"""
RescueSim — rescue agents move toward trapped people, escort them to exit.

Lifecycle per agent:
  standby → responding → on_scene → escorting → back to standby (picks next target)
"""
import math

RESCUE_STARTS = [
    {'id': 'R1', 'grid_x': 19, 'grid_y': 2,  'color': '#a78bfa'},
    {'id': 'R2', 'grid_x': 19, 'grid_y': 7,  'color': '#38bdf8'},
    {'id': 'R3', 'grid_x': 19, 'grid_y': 12, 'color': '#fb923c'},
]

EXITS = [
    {'grid_x': 19, 'grid_y': 2},
    {'grid_x': 19, 'grid_y': 7},
    {'grid_x': 19, 'grid_y': 12},
]

_agents: list = []
_initialized: bool = False

# Shared with tracksense — people confirmed out of building
rescued_people: set = set()

# Proximity radius — agent picks up anyone within this many grid cells
PICKUP_RADIUS = 3.0


def _init_agents():
    global _agents, _initialized
    _agents = [
        {
            'id': s['id'],
            'grid_x': s['grid_x'], 'grid_y': s['grid_y'],
            'start_x': s['grid_x'], 'start_y': s['grid_y'],
            'color': s['color'],
            'target': None,
            'group': [],           # list of person_ids being escorted together
            'path_history': [],
            'status': 'standby',
            'escort_exit': None,
        }
        for s in RESCUE_STARTS
    ]
    _initialized = True


def _dist(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _nearest_exit(gx, gy):
    return min(EXITS, key=lambda e: _dist(gx, gy, e['grid_x'], e['grid_y']))


def _step_toward(ax, ay, tx, ty, heatmap, max_fire=0.75):
    if ax == tx and ay == ty:
        return ax, ay
    dx = 0 if tx == ax else (1 if tx > ax else -1)
    dy = 0 if ty == ay else (1 if ty > ay else -1)
    from backend.adapters.building_adapter import grid_to_zone
    candidates = [
        (ax + dx, ay + dy),
        (ax + dx, ay),
        (ax, ay + dy),
        (ax - dx, ay + dy),
        (ax + dx, ay - dy),
    ]
    for nx, ny in candidates:
        if 0 <= nx <= 19 and 0 <= ny <= 19:
            fp = heatmap.get(grid_to_zone(nx, ny), {}).get('fire_prob', 0)
            if fp < max_fire:
                return nx, ny
    return ax, ay


def rescuesim_node(state: dict) -> dict:
    global _agents, _initialized

    if not _initialized:
        _init_agents()

    # Rescue agents operate in both scenarios — people need evacuation regardless
    # But in attacker scenario, they evacuate people away from attacker zones
    occupants = state.get('occupant_positions', [])
    heatmap   = state.get('fire_heatmap', {})
    log       = list(state.get('agent_action_log', []))

    occ_map = {o['person_id']: o for o in occupants}
    # Deploy rescue agents whenever there are at-risk people — regardless of threat level
    # (fire may be suppressed but people still need physical evacuation)
    trapped = [o for o in occupants if o['status'] == 'at_risk' and o['person_id'] not in rescued_people]

    # If no one needs rescue and all agents are standby, nothing to do
    all_standby = all(a['status'] == 'standby' for a in _agents)
    if not trapped and all_standby:
        return {'rescue_agents': [_serialise(a) for a in _agents], 'agent_action_log': log}

    # Build set of people already being handled (not yet rescued)
    # Each agent independently picks its own target — all run in parallel
    in_progress = {
        a['target'] for a in _agents
        if a['target'] and a['status'] in ('responding', 'on_scene', 'escorting')
    }

    # Log coordination overview before dispatch
    active_agents = [a for a in _agents if a['status'] != 'standby']
    if active_agents:
        summary = ', '.join(f'{a["id"]}→{a["target"] or "exit"}({a["status"]})' for a in active_agents)
        log.append(f'[RescueSim] 🤝 Active units: {summary}')

    # Assign ALL free agents simultaneously (not break-on-empty)
    for agent in _agents:
        if agent['status'] != 'standby':
            continue
        # Find nearest trapped person not already being rescued
        available = [t for t in trapped if t['person_id'] not in in_progress and t['person_id'] not in rescued_people]
        if not available:
            continue
        nearest = min(available, key=lambda t: _dist(agent['grid_x'], agent['grid_y'], t['grid_x'], t['grid_y']))
        agent['target'] = nearest['person_id']
        agent['status'] = 'responding'
        in_progress.add(nearest['person_id'])
        dist = round(_dist(agent['grid_x'], agent['grid_y'], nearest['grid_x'], nearest['grid_y']), 1)
        log.append(
            f'[RescueSim] 🚨 {agent["id"]} dispatched → {nearest["person_id"]} '
            f'at {nearest["zone"]} (dist={dist} cells)'
        )

    # Move ALL agents this cycle (parallel execution)
    for agent in _agents:
        if agent['status'] == 'standby':
            continue

        ax, ay = agent['grid_x'], agent['grid_y']
        agent['path_history'].append({'grid_x': ax, 'grid_y': ay})
        if len(agent['path_history']) > 60:
            agent['path_history'] = agent['path_history'][-60:]

        if agent['status'] == 'responding':
            target_occ = occ_map.get(agent['target'])
            if not target_occ:
                # Target already rescued by someone else
                _reset_agent(agent)
                continue
            tx, ty = target_occ['grid_x'], target_occ['grid_y']

            # Pick up any other trapped people nearby on the way
            for occ in occupants:
                pid2 = occ['person_id']
                if (occ['status'] == 'at_risk'
                        and pid2 not in rescued_people
                        and pid2 not in in_progress
                        and pid2 != agent['target']
                        and pid2 not in agent['group']
                        and _dist(ax, ay, occ['grid_x'], occ['grid_y']) <= PICKUP_RADIUS):
                    agent['group'].append(pid2)
                    in_progress.add(pid2)
                    log.append(f'[RescueSim] {agent["id"]} also picking up {pid2} (nearby)')

            if _dist(ax, ay, tx, ty) <= 1.5:
                agent['status'] = 'on_scene'
                agent['escort_exit'] = _nearest_exit(ax, ay)
                # Add primary target to group
                if agent['target'] not in agent['group']:
                    agent['group'].append(agent['target'])
                log.append(f'[RescueSim] {agent["id"]} reached {agent["target"]} — escorting group {agent["group"]} to exit')
            else:
                nx, ny = _step_toward(ax, ay, tx, ty, heatmap)
                agent['grid_x'], agent['grid_y'] = nx, ny
                from backend.adapters.building_adapter import grid_to_zone
                cur_zone = grid_to_zone(nx, ny)
                fp = heatmap.get(cur_zone, {}).get('fire_prob', 0)
                if fp > 0.1:
                    log.append(f'[RescueSim] ⚠ {agent["id"]} navigating through smoke ({cur_zone} fp={fp:.2f})')

        elif agent['status'] == 'on_scene':
            agent['status'] = 'escorting'

        elif agent['status'] == 'escorting':
            ex = agent['escort_exit']['grid_x']
            ey = agent['escort_exit']['grid_y']

            # Also pick up anyone nearby while escorting
            for occ in occupants:
                pid2 = occ['person_id']
                if (occ['status'] == 'at_risk'
                        and pid2 not in rescued_people
                        and pid2 not in in_progress
                        and pid2 not in agent['group']
                        and _dist(ax, ay, occ['grid_x'], occ['grid_y']) <= PICKUP_RADIUS):
                    agent['group'].append(pid2)
                    in_progress.add(pid2)
                    log.append(f'[RescueSim] {agent["id"]} picked up {pid2} en route to exit')

            if _dist(ax, ay, ex, ey) <= 1.5:
                # Rescue entire group
                for pid in agent['group']:
                    rescued_people.add(pid)
                    target_occ = occ_map.get(pid)
                    if target_occ:
                        target_occ['grid_x'] = ex
                        target_occ['grid_y'] = ey
                log.append(f'[RescueSim] ✅ Group {agent["group"]} RESCUED by {agent["id"]} — delivered to exit')
                # Notify other agents of remaining trapped
                remaining = [o['person_id'] for o in occupants if o['status'] == 'at_risk' and o['person_id'] not in rescued_people]
                if remaining:
                    log.append(f'[RescueSim] 📡 {agent["id"]} reports: {len(remaining)} still need rescue: {remaining}')
                _reset_agent(agent)
            else:
                nx, ny = _step_toward(ax, ay, ex, ey, heatmap, max_fire=0.9)
                agent['grid_x'], agent['grid_y'] = nx, ny
                # Move entire group with agent
                for pid in agent['group']:
                    target_occ = occ_map.get(pid)
                    if target_occ:
                        target_occ['grid_x'] = nx
                        target_occ['grid_y'] = ny

    return {
        'rescue_agents': [_serialise(a) for a in _agents],
        'occupant_positions': occupants,
        'agent_action_log': log,
    }


def _reset_agent(agent: dict):
    agent['target'] = None
    agent['group'] = []
    agent['path_history'] = []
    agent['status'] = 'standby'
    agent['grid_x'] = agent['start_x']
    agent['grid_y'] = agent['start_y']
    agent['escort_exit'] = None


def _serialise(a: dict) -> dict:
    return {k: v for k, v in a.items() if k not in ('start_x', 'start_y', 'escort_exit')}
