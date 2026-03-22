"""
FireSense agent — merges cellular automata heatmap with existing DangerManager.
"""
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.models.fire_spread import compute_heatmap, get_dangerous_zones
from backend.adapters.danger_adapter import danger_zones_to_heatmap_overlay

# Injected at server startup via set_danger_manager()
_danger_manager = None


def set_danger_manager(dm):
    global _danger_manager
    _danger_manager = dm


def firesense_node(state: dict) -> dict:
    """
    Compute merged fire heatmap from:
    1. Cellular automata on MQTT sensor readings
    2. DangerManager fire zones (existing simulation)
    """
    readings = state.get('latest_sensor_payload', {}).get('readings', [])
    prev_heatmap = state.get('fire_heatmap', {})

    # Step 1: cellular automata from sensor readings
    heatmap = compute_heatmap(readings, prev_heatmap)

    # Step 2: merge existing DangerManager overlay
    if _danger_manager is not None:
        try:
            overlay = danger_zones_to_heatmap_overlay(_danger_manager, None)
            for zone, dm_level in overlay.items():
                if zone in heatmap:
                    merged = max(heatmap[zone]['fire_prob'], dm_level)
                    heatmap[zone] = {
                        **heatmap[zone],
                        'fire_prob': round(merged, 3),
                        'danger_manager_level': dm_level,
                    }
                else:
                    heatmap[zone] = {
                        'zone': zone,
                        'fire_prob': round(dm_level, 3),
                        'smoke_prob': 0.0,
                        'predicted_spread_mins': None,
                        'danger_manager_level': dm_level,
                    }
        except Exception as e:
            pass  # DangerManager unavailable — continue with CA heatmap only

    dangerous = get_dangerous_zones(heatmap, 0.3)
    origin = (
        max(heatmap, key=lambda z: heatmap[z]['fire_prob'])
        if heatmap else None
    )
    detected_at = state.get('fire_detected_at') or (time.time() if dangerous else None)

    log = list(state.get('agent_action_log', [])) + [
        f'[FireSense] Heatmap updated. Dangerous: {dangerous}',
        f'[FireSense] Origin zone: {origin}',
    ]

    return {
        'fire_heatmap': heatmap,
        'fire_origin_zone': origin,
        'fire_detected_at': detected_at,
        'blocked_zones': dangerous,
        'agent_action_log': log,
    }
