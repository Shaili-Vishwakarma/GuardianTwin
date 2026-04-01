"""
FireBrigade agent — fire brigade units that move to fire zones and extinguish.

Lifecycle per unit:
  standby → responding → fighting → returning (walking back to exit) → standby
"""
import math

BRIGADE_STARTS = [
    {'id': 'FB1', 'grid_x': 19, 'grid_y': 0,  'color': '#f43f5e'},
    {'id': 'FB2', 'grid_x': 19, 'grid_y': 5,  'color': '#fb7185'},
]

_units: list = []
_initialized: bool = False

# Zones confirmed extinguished (persists across cycles)
extinguished_zones: set = set()


def _init_units():
    global _units, _initialized
    _units = [
        {
            'id': u['id'],
            'grid_x': u['grid_x'], 'grid_y': u['grid_y'],
            'start_x': u['grid_x'], 'start_y': u['grid_y'],
            'color': u['color'],
            'target_zone': None,
            'path_history': [],
            'status': 'standby',   # standby | responding | fighting | returning
            'fight_cycles': 0,
        }
        for u in BRIGADE_STARTS
    ]
    _initialized = True


def _dist(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _zone_center(zone: str) -> tuple:
    ZONE_GRID = {
        'F3-A': (2, 2),  'F3-B': (7, 2),  'F3-C': (12, 2), 'F3-D': (17, 2),
        'F2-A': (2, 7),  'F2-B': (7, 7),  'F2-C': (12, 7), 'F2-D': (17, 7),
        'F1-A': (2, 12), 'F1-B': (7, 12), 'F1-C': (12, 12),'F1-D': (17, 12),
    }
    return ZONE_GRID.get(zone, (10, 10))


def _step_toward(ax, ay, tx, ty):
    if ax == tx and ay == ty:
        return ax, ay
    dx = 0 if tx == ax else (1 if tx > ax else -1)
    dy = 0 if ty == ay else (1 if ty > ay else -1)
    for nx, ny in [(ax + dx, ay + dy), (ax + dx, ay), (ax, ay + dy)]:
        if 0 <= nx <= 19 and 0 <= ny <= 19:
            return nx, ny
    return ax, ay


def firebrigade_node(state: dict) -> dict:
    global _units, _initialized

    if not _initialized:
        _init_units()

    # Fire brigade only operates in fire scenario — return empty in attacker mode
    if state.get('scenario') == 'attacker':
        return {
            'fire_brigade': [],   # hide completely, not just standby
            'brigade_zones': [],
            'extinguished_zones': [],
            'agent_action_log': list(state.get('agent_action_log', [])),
        }

    heatmap = state.get('fire_heatmap', {})
    threat  = state.get('threat_level', 'none')
    log     = list(state.get('agent_action_log', []))

    # Only deploy at high/critical — but keep moving returning units regardless
    if threat not in ('high', 'critical'):
        # Still process returning units so they walk home
        _process_returning(log)
        return {
            'fire_brigade': [_ser(u) for u in _units],
            'brigade_zones': [],
            'extinguished_zones': list(extinguished_zones),
            'agent_action_log': log,
        }

    # Find fire zones sorted by intensity
    fire_zones = sorted(
        [(z, d['fire_prob']) for z, d in heatmap.items() if d['fire_prob'] > 0.3],
        key=lambda x: -x[1]
    )

    # Zones currently being fought
    in_progress = {u['target_zone'] for u in _units if u['target_zone'] and u['status'] not in ('standby', 'returning')}

    # Assign standby units to hottest unattended fire zones
    for unit in _units:
        if unit['status'] != 'standby':
            continue
        available = [(z, fp) for z, fp in fire_zones if z not in in_progress and z not in extinguished_zones]
        if not available:
            continue  # no more zones to assign — try next unit (may also have nothing)
        target_zone = available[0][0]
        unit['target_zone'] = target_zone
        unit['status'] = 'responding'
        unit['fight_cycles'] = 0
        in_progress.add(target_zone)
        log.append(f'[FireBrigade] {unit["id"]} → {target_zone} (fire_prob={available[0][1]:.2f})')

    # Move all active units
    active_brigade_zones = []
    for unit in _units:
        if unit['status'] == 'standby':
            continue

        ax, ay = unit['grid_x'], unit['grid_y']
        unit['path_history'].append({'grid_x': ax, 'grid_y': ay})
        if len(unit['path_history']) > 60:
            unit['path_history'] = unit['path_history'][-60:]

        if unit['status'] == 'responding':
            tx, ty = _zone_center(unit['target_zone'])
            if _dist(ax, ay, tx, ty) <= 2.0:
                unit['status'] = 'fighting'
                log.append(f'[FireBrigade] {unit["id"]} fighting fire at {unit["target_zone"]}')
            else:
                nx, ny = _step_toward(ax, ay, tx, ty)
                unit['grid_x'], unit['grid_y'] = nx, ny

        elif unit['status'] == 'fighting':
            active_brigade_zones.append(unit['target_zone'])
            unit['fight_cycles'] += 1
            zone_fp = heatmap.get(unit['target_zone'], {}).get('fire_prob', 0)

            if zone_fp <= 0.05:
                extinguished_zones.add(unit['target_zone'])
                log.append(
                    f'[FireBrigade] ✅ {unit["target_zone"]} EXTINGUISHED by {unit["id"]} '
                    f'({unit["fight_cycles"]} cycles) — returning to base'
                )
                # Start walking back — don't teleport
                unit['status'] = 'returning'
                unit['target_zone'] = None
                unit['fight_cycles'] = 0
            else:
                log.append(f'[FireBrigade] {unit["id"]} fighting {unit["target_zone"]} — fire_prob={zone_fp:.2f}')

        elif unit['status'] == 'returning':
            tx, ty = unit['start_x'], unit['start_y']
            if _dist(ax, ay, tx, ty) <= 1.0:
                # Arrived back at base
                unit['grid_x'], unit['grid_y'] = tx, ty
                unit['status'] = 'standby'
                unit['path_history'] = []
                log.append(f'[FireBrigade] {unit["id"]} returned to base — standby')
            else:
                nx, ny = _step_toward(ax, ay, tx, ty)
                unit['grid_x'], unit['grid_y'] = nx, ny

    return {
        'fire_brigade': [_ser(u) for u in _units],
        'brigade_zones': active_brigade_zones,
        'extinguished_zones': list(extinguished_zones),
        'agent_action_log': log,
    }


def _process_returning(log: list):
    """Move returning units toward base even when threat is low."""
    for unit in _units:
        if unit['status'] != 'returning':
            continue
        ax, ay = unit['grid_x'], unit['grid_y']
        unit['path_history'].append({'grid_x': ax, 'grid_y': ay})
        if len(unit['path_history']) > 60:
            unit['path_history'] = unit['path_history'][-60:]
        tx, ty = unit['start_x'], unit['start_y']
        if _dist(ax, ay, tx, ty) <= 1.0:
            unit['grid_x'], unit['grid_y'] = tx, ty
            unit['status'] = 'standby'
            unit['path_history'] = []
            log.append(f'[FireBrigade] {unit["id"]} returned to base — standby')
        else:
            nx, ny = _step_toward(ax, ay, tx, ty)
            unit['grid_x'], unit['grid_y'] = nx, ny


def _ser(u: dict) -> dict:
    return {k: v for k, v in u.items() if k not in ('start_x', 'start_y')}
