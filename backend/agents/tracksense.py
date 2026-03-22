"""
TrackSense agent — occupant tracking with persistent status across cycles.

Status lifecycle:
  safe (default) → at_risk (fire reaches zone) → safe (rescued/zone cleared)

People are ALWAYS visible from cycle 1. Status starts as 'safe' until fire
reaches their zone, then becomes 'at_risk' requiring physical rescue.
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.adapters.vision_adapter import load_stub_occupants
from backend.agents.rescuesim import rescued_people

STUB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'occupant_positions.json')

# Persistent memory across cycles
_status_memory: dict = {}   # person_id → status
_smoke_history: dict = {}   # zone → list of recent smoke_prob values (for trend)


def tracksense_node(state: dict) -> dict:
    global _status_memory, _smoke_history

    blocked      = state.get('blocked_zones', [])
    heatmap      = state.get('fire_heatmap', {})
    extinguished = set(state.get('extinguished_zones', []))
    log          = list(state.get('agent_action_log', []))

    prev_positions = {o['person_id']: o for o in state.get('occupant_positions', [])}

    positions = load_stub_occupants(STUB_PATH, blocked)
    if not positions:
        log.append('[TrackSense] Stub file not found')
        return {
            'occupant_positions': [],
            'unaccounted_count': state.get('total_registered_occupants', 15),
            'agent_action_log': log,
        }

    # Update smoke trend history per zone
    for zone, data in heatmap.items():
        sp = data.get('smoke_prob', 0)
        if zone not in _smoke_history:
            _smoke_history[zone] = []
        _smoke_history[zone].append(sp)
        if len(_smoke_history[zone]) > 5:
            _smoke_history[zone] = _smoke_history[zone][-5:]

    # Detect zones with rising smoke (early warning)
    rising_smoke_zones = []
    for zone, history in _smoke_history.items():
        if len(history) >= 3 and history[-1] > 0.1 and history[-1] > history[0] + 0.05:
            rising_smoke_zones.append((zone, history[-1]))

    # Detect unsafe paths (zones with moderate smoke/fire that aren't yet blocked)
    unsafe_paths = [
        z for z, d in heatmap.items()
        if 0.1 < d.get('fire_prob', 0) < 0.3 or 0.15 < d.get('smoke_prob', 0) < 0.4
    ]

    for p in positions:
        pid  = p['person_id']
        prev = _status_memory.get(pid)

        # Carry forward position updates from rescuesim (person being escorted)
        if pid in prev_positions:
            prev_occ = prev_positions[pid]
            if prev_occ.get('grid_x') != p['grid_x'] or prev_occ.get('grid_y') != p['grid_y']:
                p['grid_x'] = prev_occ['grid_x']
                p['grid_y'] = prev_occ['grid_y']
                p['zone']   = prev_occ.get('zone', p['zone'])

        zone      = p['zone']
        fire_prob = heatmap.get(zone, {}).get('fire_prob', 0)
        smoke_prob = heatmap.get(zone, {}).get('smoke_prob', 0)
        zone_clear = zone in extinguished or (zone not in blocked and fire_prob < 0.1)

        # Status resolution
        if pid in rescued_people:
            status = 'safe'
        elif prev == 'safe' and zone_clear:
            status = 'safe'
        elif prev == 'at_risk':
            # Once at_risk, stays at_risk until physically rescued
            status = 'at_risk'
        elif zone in blocked or fire_prob > 0.3:
            status = 'at_risk'
        else:
            # Default: safe (people are safe until fire reaches them)
            status = 'safe'

        p['status']    = status
        p['last_seen'] = time.time()
        p['danger_level'] = (
            'critical' if fire_prob >= 0.7 else
            'high'     if fire_prob >= 0.4 else
            'medium'   if fire_prob >= 0.1 or smoke_prob >= 0.2 else
            'low'
        )
        _status_memory[pid] = status

    total       = state.get('total_registered_occupants', 15)
    at_risk     = [p for p in positions if p['status'] == 'at_risk']
    safe_people = [p for p in positions if p['status'] == 'safe']
    unaccounted = max(0, total - len(positions))

    # Core tracking log
    log.append(
        f'[TrackSense] {len(positions)} tracked | '
        f'{len(at_risk)} at-risk | {len(safe_people)} safe | {unaccounted} unaccounted'
    )

    # Early warning: rising smoke
    if rising_smoke_zones:
        for zone, level in rising_smoke_zones:
            occupants_in_zone = [p for p in positions if p['zone'] == zone]
            if occupants_in_zone:
                pids = ', '.join(o['person_id'] for o in occupants_in_zone)
                log.append(
                    f'[TrackSense] ⚠ Smoke rising in {zone} (level={level:.2f}) '
                    f'— {pids} may need early evacuation'
                )
            else:
                log.append(f'[TrackSense] ⚠ Smoke rising in {zone} (level={level:.2f}) — zone unoccupied')

    # Unsafe path warnings
    if unsafe_paths:
        log.append(f'[TrackSense] 🚧 Paths becoming unsafe: {", ".join(unsafe_paths)} — rerouting advised')

    # At-risk people detail
    if at_risk:
        for p in at_risk:
            fp = heatmap.get(p['zone'], {}).get('fire_prob', 0)
            log.append(
                f'[TrackSense] 🔴 {p["person_id"]} at {p["zone"]} '
                f'(fire_prob={fp:.2f}) — rescue required'
            )

    return {
        'occupant_positions': positions,
        'unaccounted_count': unaccounted,
        'agent_action_log': log,
    }
