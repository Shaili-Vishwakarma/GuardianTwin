"""
AttackerSense agent — tracks attacker position and marks threatened zones.

Uses the existing AttackerSimulator from danger_simulator.py.
Replaces FireSense when scenario='attacker'.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.adapters.building_adapter import position3d_to_zone, ZONE_TO_REGION

_attacker_sim = None
_last_update = 0.0


def set_attacker_sim(sim):
    global _attacker_sim
    _attacker_sim = sim


def attackersense_node(state: dict) -> dict:
    """
    Track attacker position and mark zones as threatened.
    Runs instead of firesense when scenario='attacker'.
    """
    global _last_update
    log = list(state.get('agent_action_log', []))

    if _attacker_sim is None:
        log.append('[AttackerSense] ⚠ Attacker simulator not ready yet')
        # Return a default position so the dashboard shows something
        return {
            'attacker_position': {'grid_x': 5, 'grid_y': 5, 'zone': 'F2-B', 'floor': 2, 'danger_level': 0.9},
            'attacker_threat_zones': ['F2-B', 'F2-A', 'F2-C', 'F3-B'],
            'blocked_zones': ['F2-B'],
            'fire_heatmap': {'F2-B': {'zone': 'F2-B', 'fire_prob': 0.5, 'smoke_prob': 0.0,
                                       'predicted_spread_mins': None, 'danger_manager_level': None,
                                       'suppressed': False, 'brigade_active': False, 'extinguished': False}},
            'agent_action_log': log,
        }

    # Advance attacker simulation
    now = time.time()
    delta = now - _last_update if _last_update > 0 else 1.0
    _last_update = now

    try:
        _attacker_sim.update(delta)
    except Exception as e:
        log.append(f'[AttackerSense] Sim update error: {e}')

    # Get attacker position
    danger_zones = _attacker_sim.get_danger_zones()
    if not danger_zones:
        return {
            'attacker_position': {},
            'attacker_threat_zones': [],
            'blocked_zones': [],
            'fire_heatmap': {},
            'agent_action_log': log,
        }

    attacker_zone_obj = danger_zones[0]
    pos = attacker_zone_obj.position
    zone_label = position3d_to_zone(pos)

    attacker_pos = {
        'grid_x': min(19, max(0, int(pos.x))),
        'grid_y': min(19, max(0, int(pos.y))),
        'zone': zone_label,
        'floor': pos.floor,
        'danger_level': attacker_zone_obj.danger_level,
    }

    # Mark attacker zone + adjacent zones as threatened
    from backend.models.fire_spread import ZONE_ADJACENCY
    threatened = [zone_label]
    for adj in ZONE_ADJACENCY.get(zone_label, []):
        threatened.append(adj)

    # Build a pseudo-heatmap so the floor plan can show threat overlay
    # Use danger_level as fire_prob equivalent for display
    heatmap = {}
    for z in threatened:
        dist_factor = 1.0 if z == zone_label else 0.4
        heatmap[z] = {
            'zone': z,
            'fire_prob': round(attacker_zone_obj.danger_level * dist_factor, 3),
            'smoke_prob': 0.0,
            'predicted_spread_mins': None,
            'danger_manager_level': None,
            'suppressed': False,
            'brigade_active': False,
            'extinguished': False,
        }

    log.append(
        f'[AttackerSense] 🔴 Attacker at {zone_label} '
        f'(floor {pos.floor}, danger={attacker_zone_obj.danger_level:.2f})'
    )
    log.append(f'[AttackerSense] Threatened zones: {threatened}')

    return {
        'attacker_position': attacker_pos,
        'attacker_threat_zones': threatened,
        'blocked_zones': threatened,
        'fire_heatmap': heatmap,
        'agent_action_log': log,
    }
