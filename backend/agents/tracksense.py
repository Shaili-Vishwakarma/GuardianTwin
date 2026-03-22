"""
TrackSense agent — occupant tracking via VideoAnalyzer or stub JSON fallback.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.adapters.vision_adapter import video_analysis_to_occupants, load_stub_occupants

STUB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'occupant_positions.json')

# Injected at server startup if live video is available
_video_analyzer = None


def set_video_analyzer(va):
    global _video_analyzer
    _video_analyzer = va


def tracksense_node(state: dict) -> dict:
    """
    Locate occupants using live VideoAnalyzer or stub JSON fallback.
    Occupants in blocked_zones are marked at_risk.
    """
    blocked = state.get('blocked_zones', [])
    vision_data = state.get('vision_analysis')
    log = list(state.get('agent_action_log', []))

    if vision_data and _video_analyzer is not None:
        people_data = vision_data.get('people_data', {})
        position_data = vision_data.get('position_data', {})
        positions = video_analysis_to_occupants(people_data, position_data, blocked)
    else:
        positions = load_stub_occupants(STUB_PATH, blocked)
        if not positions:
            log.append('[TrackSense] Stub file not found')

    unaccounted = state.get('total_registered_occupants', 4) - len(positions)

    log += [
        f'[TrackSense] Located {len(positions)} occupants. Unaccounted: {unaccounted}',
        f'[TrackSense] At risk: {[p["person_id"] for p in positions if p["status"] == "at_risk"]}',
    ]

    return {
        'occupant_positions': positions,
        'unaccounted_count': unaccounted,
        'agent_action_log': log,
    }
