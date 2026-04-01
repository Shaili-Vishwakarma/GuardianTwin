"""
Optional LangGraph @tool functions for GuardianTwin agents.
These tools can be bound to LLM agents for structured tool-calling.
Agents work without this file — it is purely additive.
"""
from langchain_core.tools import tool


@tool
def get_fire_status(zone: str) -> dict:
    """Get the current fire probability and smoke level for a specific zone.

    Args:
        zone: Zone label e.g. 'F3-B'

    Returns:
        dict with fire_prob, smoke_prob, suppressed, brigade_active
    """
    # Implemented at runtime by injecting current heatmap
    return {'zone': zone, 'fire_prob': 0.0, 'smoke_prob': 0.0,
            'suppressed': False, 'brigade_active': False}


@tool
def get_occupant_status(person_id: str) -> dict:
    """Get the current status and location of a specific occupant.

    Args:
        person_id: Occupant ID e.g. 'P01'

    Returns:
        dict with person_id, zone, status, danger_level
    """
    return {'person_id': person_id, 'zone': 'unknown',
            'status': 'unknown', 'danger_level': 'unknown'}


@tool
def get_evacuation_route(person_id: str) -> list:
    """Get the computed evacuation route for a specific occupant.

    Args:
        person_id: Occupant ID e.g. 'P01'

    Returns:
        list of RouteWaypoint dicts with grid_x, grid_y, zone
    """
    return []


@tool
def get_building_systems_status() -> dict:
    """Get the current status of all building safety systems.

    Returns:
        dict with hvac_shutdown, elevators_recalled, emergency_lighting,
        suppression_active zones, extinguished zones
    """
    return {
        'hvac_shutdown': False,
        'elevators_recalled': False,
        'emergency_lighting': False,
        'suppression_active': [],
        'extinguished_zones': [],
    }


@tool
def get_threat_summary() -> dict:
    """Get a summary of the current emergency threat level and fire origin.

    Returns:
        dict with threat_level, fire_origin_zone, blocked_zones, unaccounted_count
    """
    return {
        'threat_level': 'none',
        'fire_origin_zone': None,
        'blocked_zones': [],
        'unaccounted_count': 0,
    }


# All tools available for binding to LLM agents
ALL_TOOLS = [
    get_fire_status,
    get_occupant_status,
    get_evacuation_route,
    get_building_systems_status,
    get_threat_summary,
]
