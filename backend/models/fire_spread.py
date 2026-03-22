"""
Deterministic cellular automata fire spread model.
No training required. Runs in under 5ms per cycle.
"""

SPREAD_RATE = 0.015  # probability per second fire moves to adjacent zone

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


def compute_heatmap(readings: list, prev_heatmap: dict = None, delta_t: float = 1.0) -> dict:
    """
    Compute fire heatmap from sensor readings using cellular automata.

    Args:
        readings: list of zone sensor dicts with smoke_ppm, temp_c, flame
        prev_heatmap: previous heatmap for spread propagation
        delta_t: seconds since last update

    Returns:
        dict mapping zone label → ZoneHeat-compatible dict
    """
    heatmap = (prev_heatmap or {}).copy()

    for r in readings:
        zone = r.get('zone')
        if not zone:
            continue
        smoke_prob = min(1.0, r.get('smoke_ppm', 0) / 500.0)
        fire_prob = max(0.0, min(1.0, (r.get('temp_c', 20) - 25) / 275.0))
        if r.get('flame'):
            fire_prob = max(fire_prob, 0.9)
        heatmap[zone] = {
            'zone': zone,
            'fire_prob': round(fire_prob, 3),
            'smoke_prob': round(smoke_prob, 3),
            'predicted_spread_mins': _spread_time(fire_prob),
            'danger_manager_level': heatmap.get(zone, {}).get('danger_manager_level'),
        }

    # Cellular automata spread
    spread = {}
    for zone, data in heatmap.items():
        if data['fire_prob'] > 0.1:
            for adj in ZONE_ADJACENCY.get(zone, []):
                sp = data['fire_prob'] * SPREAD_RATE * delta_t
                spread[adj] = max(spread.get(adj, 0.0), sp)

    for zone, prob in spread.items():
        if zone not in heatmap:
            heatmap[zone] = {
                'zone': zone, 'fire_prob': 0.0, 'smoke_prob': 0.0,
                'predicted_spread_mins': None, 'danger_manager_level': None,
            }
        heatmap[zone]['fire_prob'] = round(max(heatmap[zone]['fire_prob'], prob), 3)

    return heatmap


def get_dangerous_zones(heatmap: dict, threshold: float = 0.3) -> list:
    """Return list of zone labels where fire_prob >= threshold."""
    return [z for z, d in heatmap.items() if d['fire_prob'] >= threshold]


def _spread_time(fp: float) -> float:
    """Estimate minutes until fire spreads from a zone."""
    if fp > 0.05:
        return round((0.5 / (fp * SPREAD_RATE)) / 60, 1)
    return None
