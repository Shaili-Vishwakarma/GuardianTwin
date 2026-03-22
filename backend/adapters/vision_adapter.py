"""
Adapter: VideoAnalyzer (existing) ↔ GuardianTwin OccupantPosition list.
"""
import json
import time


def _pixel_to_grid(px: int, py: int, frame_w: int = 1280, frame_h: int = 720):
    """Map pixel centre coords to 20×20 grid coords."""
    gx = min(19, int(px / frame_w * 20))
    gy = min(19, int(py / frame_h * 20))
    return gx, gy


def _grid_to_zone(gx: int, gy: int) -> str:
    """Map grid coords to zone label."""
    floor = 3 - gy // 5
    floor = max(1, min(3, floor))
    col = min(3, gx // 5)
    return f'F{floor}-{["A", "B", "C", "D"][col]}'


def video_analysis_to_occupants(people_data: dict, position_data: dict,
                                  blocked_zones: list) -> list:
    """
    Convert VideoAnalyzer output to OccupantPosition list.

    Args:
        people_data: PeopleDetector output {'people': [...], 'count': N}
        position_data: PositionEstimator output {'positions': [...]}
        blocked_zones: list of zone labels currently on fire

    Returns:
        list of OccupantPosition-compatible dicts
    """
    occupants = []
    for person in people_data.get('people', []):
        pid = str(person['id'])
        bbox = person.get('position', [0, 0, 100, 100])
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        gx, gy = _pixel_to_grid(cx, cy)
        zone = _grid_to_zone(gx, gy)

        pos_3d = next(
            (p for p in position_data.get('positions', [])
             if str(p.get('id')) == f'person_{pid}'),
            None,
        )
        floor = pos_3d['floor'] if pos_3d else int(zone[1])
        coords_3d = pos_3d['coords'] if pos_3d else None
        status = 'at_risk' if zone in blocked_zones else 'unknown'

        occupants.append({
            'person_id': f'P{pid}',
            'zone': zone,
            'grid_x': gx,
            'grid_y': gy,
            'floor': floor,
            'status': status,
            'last_seen': time.time(),
            'coords_3d': coords_3d,
            'danger_level': person.get('danger_level', 'unknown'),
        })
    return occupants


def load_stub_occupants(stub_path: str, blocked_zones: list) -> list:
    """Load stub occupant_positions.json and apply current blocked zones."""
    try:
        with open(stub_path) as f:
            positions = json.load(f)
    except FileNotFoundError:
        return []

    for p in positions:
        p['last_seen'] = time.time()
        p.setdefault('floor', int(p['zone'][1]))
        p.setdefault('coords_3d', None)
        p.setdefault('danger_level', None)
        if p['zone'] in blocked_zones:
            p['status'] = 'at_risk'
    return positions
