"""
Deterministic cellular automata fire spread model.
Supports suppression (sprinklers) and fire brigade extinguishing.

Key design: suppressed/brigade zones use the PREVIOUS heatmap value as base
and apply reduction each cycle — raw sensor readings cannot override suppression
progress once a zone is being actively fought.
"""

SPREAD_RATE = 0.06   # per cycle — fire spreads to adjacent zones visibly within ~5 cycles

ZONE_ADJACENCY = {
    'F3-A': ['F3-B', 'F2-A'],
    'F3-B': ['F3-A', 'F3-C', 'F2-B'],
    'F3-C': ['F3-B', 'F3-D', 'F2-C'],
    'F3-D': ['F3-C', 'F2-D'],
    'F2-A': ['F2-B', 'F1-A', 'F3-A'],
    'F2-B': ['F2-A', 'F2-C', 'F1-B', 'F3-B'],
    'F2-C': ['F2-B', 'F2-D', 'F1-C', 'F3-C'],
    'F2-D': ['F2-C', 'F1-D', 'F3-D'],
    'F1-A': ['F1-B', 'F2-A'],
    'F1-B': ['F1-A', 'F1-C', 'F2-B'],
    'F1-C': ['F1-B', 'F1-D', 'F2-C'],
    'F1-D': ['F1-C', 'F2-D'],
}

# How much fire_prob drops per cycle under suppression
# Brigade is strong enough to fully extinguish in ~8 cycles (~40s)
SPRINKLER_REDUCTION = 0.08   # sprinklers: slow reduction, keeps fire contained
BRIGADE_REDUCTION   = 0.15   # brigade: fast reduction, extinguishes in ~7 cycles


def compute_heatmap(readings: list, prev_heatmap: dict = None,
                    suppression_zones: list = None,
                    brigade_zones: list = None,
                    extinguished_zones: list = None,
                    delta_t: float = 1.0) -> dict:
    """
    Compute fire heatmap from sensor readings using cellular automata.

    Suppression logic:
    - Normal zones: fire_prob derived from sensor reading (temp/flame/smoke)
    - Suppressed zones: fire_prob = prev_value - SPRINKLER_REDUCTION (sensor ignored)
    - Brigade zones: fire_prob = prev_value - BRIGADE_REDUCTION (sensor ignored)
    - Extinguished zones: fire_prob forced to 0.0 permanently
    """
    prev = (prev_heatmap or {}).copy()
    heatmap = {}
    suppression_zones  = suppression_zones  or []
    brigade_zones      = brigade_zones      or []
    extinguished_zones = extinguished_zones or []

    # Build a lookup of current readings by zone
    reading_by_zone = {r['zone']: r for r in readings if r.get('zone')}

    # Process all known zones (union of prev + current readings)
    all_zones = set(prev.keys()) | set(reading_by_zone.keys())

    for zone in all_zones:
        prev_fp    = prev.get(zone, {}).get('fire_prob', 0.0)
        prev_smoke = prev.get(zone, {}).get('smoke_prob', 0.0)
        r          = reading_by_zone.get(zone)

        # Extinguished zones are permanently zeroed — sensor readings ignored
        if zone in extinguished_zones:
            heatmap[zone] = {
                'zone': zone,
                'fire_prob': 0.0,
                'smoke_prob': max(0.0, prev_smoke - 0.05),
                'predicted_spread_mins': None,
                'danger_manager_level': prev.get(zone, {}).get('danger_manager_level'),
                'suppressed': False,
                'brigade_active': False,
                'extinguished': True,
            }
            continue

        # Brigade zones: ignore sensor, apply strong reduction to prev value
        if zone in brigade_zones:
            new_fp = max(0.0, prev_fp - BRIGADE_REDUCTION)
            smoke  = max(0.0, (r['smoke_ppm'] / 500.0 if r else prev_smoke) - 0.05)
            heatmap[zone] = {
                'zone': zone,
                'fire_prob': round(new_fp, 3),
                'smoke_prob': round(min(1.0, smoke), 3),
                'predicted_spread_mins': _spread_time(new_fp),
                'danger_manager_level': prev.get(zone, {}).get('danger_manager_level'),
                'suppressed': False,
                'brigade_active': True,
                'extinguished': False,
            }
            continue

        # Suppressed zones: ignore sensor, apply moderate reduction to prev value
        if zone in suppression_zones:
            new_fp = max(0.0, prev_fp - SPRINKLER_REDUCTION)
            smoke  = max(0.0, (r['smoke_ppm'] / 500.0 if r else prev_smoke) - 0.02)
            heatmap[zone] = {
                'zone': zone,
                'fire_prob': round(new_fp, 3),
                'smoke_prob': round(min(1.0, smoke), 3),
                'predicted_spread_mins': _spread_time(new_fp),
                'danger_manager_level': prev.get(zone, {}).get('danger_manager_level'),
                'suppressed': True,
                'brigade_active': False,
                'extinguished': False,
            }
            continue

        # Normal zone: derive fire_prob from sensor reading
        if r:
            smoke_prob = min(1.0, r.get('smoke_ppm', 0) / 500.0)
            fire_prob  = max(0.0, min(1.0, (r.get('temp_c', 20) - 25) / 275.0))
            if r.get('flame'):
                fire_prob = max(fire_prob, 0.9)
        else:
            # No reading this cycle — decay slightly
            fire_prob  = max(0.0, prev_fp - 0.01)
            smoke_prob = max(0.0, prev_smoke - 0.01)

        heatmap[zone] = {
            'zone': zone,
            'fire_prob': round(fire_prob, 3),
            'smoke_prob': round(smoke_prob, 3),
            'predicted_spread_mins': _spread_time(fire_prob),
            'danger_manager_level': prev.get(zone, {}).get('danger_manager_level'),
            'suppressed': False,
            'brigade_active': False,
            'extinguished': False,
        }

    # Cellular automata spread — only from unsuppressed, non-extinguished zones
    spread = {}
    for zone, data in heatmap.items():
        active = (
            data['fire_prob'] > 0.1
            and not data.get('suppressed')
            and not data.get('brigade_active')
            and not data.get('extinguished')
        )
        if active:
            for adj in ZONE_ADJACENCY.get(zone, []):
                sp = data['fire_prob'] * SPREAD_RATE * delta_t
                spread[adj] = max(spread.get(adj, 0.0), sp)

    for zone, prob in spread.items():
        # Don't spread into suppressed/brigade/extinguished zones
        if zone in suppression_zones or zone in brigade_zones or zone in extinguished_zones:
            continue
        if zone not in heatmap:
            heatmap[zone] = {
                'zone': zone, 'fire_prob': 0.0, 'smoke_prob': 0.0,
                'predicted_spread_mins': None, 'danger_manager_level': None,
                'suppressed': False, 'brigade_active': False, 'extinguished': False,
            }
        heatmap[zone]['fire_prob'] = round(max(heatmap[zone]['fire_prob'], prob), 3)

    return heatmap


def get_dangerous_zones(heatmap: dict, threshold: float = 0.3) -> list:
    """Return list of zone labels where fire_prob >= threshold."""
    return [z for z, d in heatmap.items() if d['fire_prob'] >= threshold]


def _spread_time(fp: float) -> float:
    """Estimate minutes until fire spreads from a zone."""
    if fp and fp > 0.05:
        return round((0.5 / (fp * SPREAD_RATE)) / 60, 1)
    return None
