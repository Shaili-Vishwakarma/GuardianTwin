"""
RoutePilot agent — evacuation route computation.
Tries fast grid A* first, falls back to Building3D NetworkX A*.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.models.router import compute_routes as grid_astar_routes
from backend.adapters.building_adapter import find_safe_route_via_building3d
from backend.adapters.danger_adapter import update_building_from_heatmap

# Module-level Building3D singleton — initialized once at startup
_building = None


def get_building():
    global _building
    if _building is None:
        from building_navigator import Building3D
        _building = Building3D()
    return _building


def routepilot_node(state: dict) -> dict:
    """
    Compute evacuation routes for all occupants.
    Routes avoid zones with fire_prob > 0.3.
    Falls back to Building3D A* if grid A* finds no path.
    """
    occupants = state.get('occupant_positions', [])
    heatmap = state.get('fire_heatmap', {})
    log = list(state.get('agent_action_log', []))

    if not occupants or not heatmap:
        return {'agent_action_log': log + ['[RoutePilot] Waiting for data']}

    # Sync fire heatmap into Building3D danger zones
    building = get_building()
    try:
        update_building_from_heatmap(heatmap, building)
    except Exception:
        pass

    # Fast grid A*
    routes = grid_astar_routes(occupants, heatmap)

    # Fallback to Building3D A* for any occupant without a route
    blocked = state.get('blocked_zones', [])
    for occ in occupants:
        pid = occ['person_id']
        if pid not in routes:
            try:
                fallback = find_safe_route_via_building3d(occ, blocked, building)
                if fallback:
                    routes[pid] = fallback
                    log.append(f'[RoutePilot] Used Building3D fallback for {pid}')
            except Exception:
                pass

    log += [
        f'[RoutePilot] Routes computed for {len(routes)} occupants',
        f'[RoutePilot] Route lengths: { {pid: len(r) for pid, r in routes.items()} }',
    ]

    return {'safe_routes': routes, 'agent_action_log': log}
