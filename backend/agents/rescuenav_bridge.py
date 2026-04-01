"""
RescueNav Bridge — connects the existing RescueSimulationEngine (3D NeMo agents)
to the GuardianTwin EmergencyState.

Runs RescueSimulationEngine in a background thread. After each mission completes,
pushes agent paths, mission result, and learning stats into shared state so the
dashboard can show real 3D-pathfound agent data alongside the live fire response.
"""
import sys
import os
import threading
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Shared mission state — updated by background thread, read by the bridge node
_mission_lock = threading.Lock()
_latest_mission: dict = {}          # last completed mission result
_mission_stats: dict = {}           # aggregated stats from atlas_learning_db
_nemo_agent_paths: list = []        # agent paths from last mission (grid coords)
_mission_running: bool = False
_mission_count: int = 0


def _position3d_to_grid(pos) -> dict:
    """Convert Building3D Position3D to grid coords for the dashboard.
    
    Building3D: x=col*cell_size, y=row*cell_size, floor=floor_index
    Grid: grid_x=col (0-19), grid_y=row (0-19)
    """
    from backend.adapters.building_adapter import position3d_to_zone
    # x maps to grid_x (column), y maps to grid_y (row)
    grid_x = min(19, max(0, int(pos.x)))
    grid_y = min(19, max(0, int(pos.y)))
    return {
        'grid_x': grid_x,
        'grid_y': grid_y,
        'zone': position3d_to_zone(pos),
        'floor': pos.floor,
    }


def _run_mission_async(scenario: str, num_agents: int, db):
    """Run one RescueSimulationEngine mission in a background thread."""
    global _latest_mission, _nemo_agent_paths, _mission_running, _mission_count

    try:
        from rescue_simulation import RescueSimulationEngine
        from building_navigator import Building3D
        from danger_simulator import DangerManager

        print(f'[RescueNav] Starting {scenario} mission with {num_agents} agents...')
        _mission_running = True

        building = Building3D()
        dm = DangerManager(building, scenario=scenario)

        from nemo_rescue_agents import CollaborativeRescueSwarm
        learning_data = {}
        if db:
            try:
                learning_data = db.get_learning_data(scenario)
            except Exception:
                pass

        swarm = CollaborativeRescueSwarm(
            num_agents=num_agents,
            building=building,
            danger_manager=dm,
            learning_data=learning_data,
        )
        mission = swarm.execute_mission(max_time=60.0)

        # Store mission in atlas db
        if db:
            try:
                db.store_mission(mission)
            except Exception:
                pass

        # Convert agent paths to grid coords for dashboard
        paths = []
        for agent_state in mission.agents:
            path_grid = [_position3d_to_grid(p) for p in agent_state.path_taken]
            paths.append({
                'agent_id': agent_state.agent_id,
                'is_alive': agent_state.is_alive,
                'has_child': agent_state.has_child,
                'health': round(agent_state.health, 2),
                'cumulative_danger': round(agent_state.cumulative_danger, 2),
                'path': path_grid[-20:],  # last 20 steps for display
            })

        # Get updated stats
        stats = {}
        if db:
            try:
                stats = db.get_mission_statistics(scenario)
            except Exception:
                pass

        with _mission_lock:
            _mission_count += 1
            _latest_mission = {
                'mission_id': mission.mission_id,
                'scenario': mission.scenario,
                'success': mission.success,
                'total_time': round(mission.total_time, 1),
                'reason_failed': mission.reason_failed,
                'num_agents': len(mission.agents),
                'agents_alive': sum(1 for a in mission.agents if a.is_alive),
                'agents_rescued': sum(1 for a in mission.agents if a.has_child),
                'mission_number': _mission_count,
            }
            _nemo_agent_paths = paths
            _mission_stats = stats

        result = 'SUCCESS' if mission.success else f'FAILED ({mission.reason_failed})'
        print(f'[RescueNav] Mission {_mission_count} complete: {result} in {mission.total_time:.1f}s')

    except Exception as e:
        print(f'[RescueNav] Mission error: {e}')
    finally:
        _mission_running = False


def start_mission(scenario: str = 'fire', num_agents: int = 3, db=None):
    """Trigger a new RescueSimulationEngine mission in the background."""
    global _mission_running
    if _mission_running:
        return  # Don't start another while one is running
    t = threading.Thread(
        target=_run_mission_async,
        args=(scenario, num_agents, db),
        daemon=True,
    )
    t.start()


def rescuenav_bridge_node(state: dict) -> dict:
    """
    LangGraph node — injects latest RescueNav mission data into EmergencyState.
    Triggers a new mission when fire is first detected and no mission is running.
    """
    log = list(state.get('agent_action_log', []))
    threat = state.get('threat_level', 'none')

    with _mission_lock:
        latest = dict(_latest_mission)
        stats  = dict(_mission_stats)
        paths  = list(_nemo_agent_paths)
        running = _mission_running

    # Auto-trigger a mission when fire is detected
    # Guard: don't trigger during pytest runs
    import sys
    in_test = 'pytest' in sys.modules
    if threat in ('high', 'critical') and not running and not latest and not in_test:
        log.append('[RescueNav] 🚀 Triggering 3D rescue simulation mission...')
        start_mission(scenario='fire', num_agents=3, db=_db_ref)

    # Log mission result when available
    if latest and latest.get('mission_number', 0) > 0:
        prev_num = state.get('mission_history', {}).get('mission_number', 0)
        if latest['mission_number'] > prev_num:
            result = '✅ SUCCESS' if latest['success'] else f'❌ FAILED'
            log.append(
                f'[RescueNav] Mission #{latest["mission_number"]} {result} '
                f'— {latest["agents_alive"]}/{latest["num_agents"]} agents alive, '
                f'{latest["total_time"]}s'
            )

    updates = {
        'agent_action_log': log,
        'mission_history': latest,
        'mission_stats': stats,
        'nemo_agent_paths': paths,
    }
    return updates


# Module-level db reference — set at server startup
_db_ref = None


def set_db(db):
    global _db_ref
    _db_ref = db
