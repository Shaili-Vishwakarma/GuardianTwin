"""
FireSense agent — fire detection and heatmap computation via cellular automata.

Fire starts ONLY from sensor readings (F3-B at T+30s).
Spread is handled purely by the CA model via ZONE_ADJACENCY.
DangerManager overlay is intentionally disabled — it caused multi-zone ignition.
"""
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.models.fire_spread import compute_heatmap, get_dangerous_zones, ZONE_ADJACENCY

_danger_manager = None


def set_danger_manager(dm):
    global _danger_manager
    _danger_manager = dm


def firesense_node(state: dict) -> dict:
    readings           = state.get('latest_sensor_payload', {}).get('readings', [])
    prev_heatmap       = state.get('fire_heatmap', {})
    suppression_zones  = state.get('suppression_active', [])
    brigade_zones      = state.get('brigade_zones', [])
    extinguished_zones = state.get('extinguished_zones', [])

    # CA model — single source of truth for fire spread
    heatmap = compute_heatmap(
        readings, prev_heatmap,
        suppression_zones=suppression_zones,
        brigade_zones=brigade_zones,
        extinguished_zones=extinguished_zones,
    )

    # NOTE: DangerManager overlay intentionally skipped — it injects fire into
    # multiple zones simultaneously, bypassing the CA spread model.

    dangerous = get_dangerous_zones(heatmap, 0.3)

    # Lock fire origin on first detection — never changes
    prev_origin = state.get('fire_origin_zone')
    if prev_origin:
        origin = prev_origin
    elif dangerous:
        origin = max(heatmap, key=lambda z: heatmap[z]['fire_prob'])
    else:
        origin = None

    detected_at = state.get('fire_detected_at') or (time.time() if dangerous else None)

    log = list(state.get('agent_action_log', []))

    # Pre-fire early warning: smoke rising but not yet dangerous
    pre_fire_zones = [
        (z, d) for z, d in heatmap.items()
        if 0.05 < d.get('smoke_prob', 0) < 0.4 and d.get('fire_prob', 0) < 0.3
    ]
    if pre_fire_zones:
        for zone, data in pre_fire_zones:
            sp = data['smoke_prob']
            log.append(f'[FireSense] 🌫 Smoke detected in {zone}: {sp:.2f} — monitoring')

    # Active fire zones
    active_zones = [(z, d) for z, d in heatmap.items() if d.get('fire_prob', 0) >= 0.3]
    for zone, data in active_zones:
        fp = data['fire_prob']
        sp = data.get('smoke_prob', 0)
        suppressed = data.get('suppressed', False)
        brigade    = data.get('brigade_active', False)
        status_tag = '💧 suppressed' if suppressed else ('🚒 brigade' if brigade else '🔥 active')
        log.append(f'[FireSense] {status_tag} {zone}: fire={fp:.2f} smoke={sp:.2f}')

    # Spread prediction
    if dangerous:
        for zone in dangerous:
            fp = heatmap[zone]['fire_prob']
            neighbors = ZONE_ADJACENCY.get(zone, [])
            at_risk_neighbors = [
                n for n in neighbors
                if n not in dangerous and n not in extinguished_zones
                and heatmap.get(n, {}).get('fire_prob', 0) < 0.3
            ]
            if at_risk_neighbors:
                spread_mins = round((0.3 / (fp * 0.06)) / 60, 1) if fp > 0 else '?'
                log.append(
                    f'[FireSense] ⚡ {zone} may spread to {at_risk_neighbors} '
                    f'in ~{spread_mins} min — path unsafe'
                )

    if not dangerous and not pre_fire_zones:
        log.append('[FireSense] All zones clear')
    elif dangerous:
        log.append(f'[FireSense] 🔥 Dangerous zones: {dangerous} | Origin: {origin}')

    return {
        'fire_heatmap':      heatmap,
        'fire_origin_zone':  origin,
        'fire_detected_at':  detected_at,
        'blocked_zones':     dangerous,
        'agent_action_log':  log,
    }
