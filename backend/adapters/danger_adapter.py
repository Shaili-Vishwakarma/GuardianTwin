"""
Adapter: DangerManager (existing) ↔ GuardianTwin ZoneHeat heatmap.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from building_navigator import Building3D, Position3D
from backend.adapters.building_adapter import ZONE_TO_REGION, position3d_to_zone


def danger_zones_to_heatmap_overlay(danger_manager, building) -> dict:
    """
    Convert DangerManager fire zones to a zone → danger_level dict.
    Only fire-type zones are included (attacker zones excluded).

    Args:
        danger_manager: existing DangerManager instance
        building: Building3D instance (unused but kept for signature consistency)

    Returns:
        dict mapping zone label → max danger_level (0.0–1.0)
    """
    overlay = {}
    for zone in danger_manager.get_all_danger_zones():
        if zone.type != 'fire':
            continue
        zone_label = position3d_to_zone(zone.position)
        overlay[zone_label] = max(overlay.get(zone_label, 0.0), zone.danger_level)
    return overlay


def update_building_from_heatmap(heatmap: dict, building: Building3D):
    """
    Push GuardianTwin fire heatmap into Building3D danger zones so that
    Building3D.find_path() uses current fire probabilities.

    Resets all existing danger levels before applying new values.
    """
    danger_list = []
    for zone_label, heat in heatmap.items():
        region = ZONE_TO_REGION.get(zone_label)
        if region is None:
            continue
        row, col = region
        center_x = float(col + 2) * building.cell_size
        center_y = float(row + 2) * building.cell_size
        floor_num = int(zone_label[1])
        pos = Position3D(
            x=center_x,
            y=center_y,
            z=float(floor_num) * building.floor_height,
            floor=floor_num,
        )
        danger_list.append((pos, heat['fire_prob']))
    building.update_danger_zones(danger_list)
