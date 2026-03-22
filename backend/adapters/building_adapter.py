"""
Adapter: Building3D (existing) ↔ GuardianTwin zone grid.

Zone layout on 20×20 grid:
  cols 0–4   cols 5–9   cols 10–14  cols 15–19
  ┌──────────┬──────────┬───────────┬──────────┐
  │  F3-A    │  F3-B    │  F3-C     │  F3-D    │  rows 0–4   (floor 3)
  ├──────────┼──────────┼───────────┼──────────┤
  │  F2-A    │  F2-B    │  F2-C     │  F2-D    │  rows 5–9   (floor 2)
  ├──────────┼──────────┼───────────┼──────────┤
  │  F1-A    │  F1-B    │  F1-C     │  F1-D    │  rows 10–14 (floor 1)
  └──────────┴──────────┴───────────┴──────────┘
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from building_navigator import Building3D, Position3D
from typing import Optional

ZONE_TO_REGION = {
    'F3-A': (0, 0),  'F3-B': (0, 5),  'F3-C': (0, 10), 'F3-D': (0, 15),
    'F2-A': (5, 0),  'F2-B': (5, 5),  'F2-C': (5, 10), 'F2-D': (5, 15),
    'F1-A': (10, 0), 'F1-B': (10, 5), 'F1-C': (10, 10), 'F1-D': (10, 15),
}

ZONE_FLOOR = {'F1': 1, 'F2': 2, 'F3': 3}


def zone_to_position3d(zone: str, grid_x: int, grid_y: int,
                        building: Building3D) -> Optional[Position3D]:
    """Convert zone label + grid coords to Building3D Position3D."""
    floor_label = zone[:2]
    floor = ZONE_FLOOR.get(floor_label, 1)
    x = float(grid_x) * building.cell_size
    y = float(grid_y) * building.cell_size
    z = float(floor) * building.floor_height
    return Position3D(x=x, y=y, z=z, floor=floor)


def position3d_to_zone(pos: Position3D) -> str:
    """Convert Building3D Position3D to zone label."""
    col_idx = min(int(pos.x / 5.0), 3)
    zone_letter = ['A', 'B', 'C', 'D'][col_idx]
    floor = max(1, min(3, pos.floor))
    return f'F{floor}-{zone_letter}'


def find_safe_route_via_building3d(occupant: dict, blocked_zones: list,
                                    building: Building3D) -> Optional[list]:
    """
    Use Building3D.find_path() (NetworkX A* with danger avoidance)
    as a fallback route planner for one occupant.

    Returns list of RouteWaypoint dicts or None.
    """
    start = zone_to_position3d(
        occupant['zone'], occupant['grid_x'], occupant['grid_y'], building
    )
    if start is None or not building.exits:
        return None

    goal = min(building.exits, key=lambda e: start.distance_to(e))
    path = building.find_path(start, goal, avoid_danger=True)
    if not path:
        return None

    return [
        {
            'grid_x': int(p.x / building.cell_size),
            'grid_y': int(p.y / building.cell_size),
            'zone': position3d_to_zone(p),
        }
        for p in path
    ]


def grid_to_zone(grid_x: int, grid_y: int) -> str:
    """Convert 20x20 grid coords to zone label."""
    col = min(3, grid_x // 5)
    floor = 3 - min(2, grid_y // 5)
    return f'F{floor}-{["A","B","C","D"][col]}'


def update_building_from_heatmap(heatmap: dict, building: Building3D):
    """Sync fire heatmap danger levels into Building3D danger zones."""
    for zone, data in heatmap.items():
        if data.get('fire_prob', 0) > 0.3:
            reg = ZONE_TO_REGION.get(zone)
            if reg:
                row, col = reg
                for r in range(row, row + 5):
                    for c in range(col, col + 5):
                        pos = Position3D(
                            x=float(c) * building.cell_size,
                            y=float(r) * building.cell_size,
                            z=float(ZONE_FLOOR.get(zone[:2], 1)) * building.floor_height,
                            floor=ZONE_FLOOR.get(zone[:2], 1),
                        )
                        building.mark_danger(pos, data['fire_prob'])
