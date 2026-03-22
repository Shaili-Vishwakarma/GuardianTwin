"""
EmergencyState — single source of truth shared by all LangGraph agents.
Extended from the base MVP spec to include existing system data structures.
"""
from typing import TypedDict, Literal, Optional, Annotated
from langgraph.graph.message import add_messages


class ZoneHeat(TypedDict):
    zone: str
    fire_prob: float                        # 0.0–1.0 from cellular automata
    smoke_prob: float                       # 0.0–1.0 from sensor ppm
    predicted_spread_mins: Optional[float]
    danger_manager_level: Optional[float]   # 0.0–1.0 from existing DangerManager


class OccupantPosition(TypedDict):
    person_id: str
    zone: str                               # e.g. 'F3-B'
    grid_x: int                             # 0–19
    grid_y: int                             # 0–19
    floor: int                              # 1–3
    status: Literal['safe', 'at_risk', 'unknown']
    last_seen: float                        # unix timestamp
    coords_3d: Optional[list]              # [x, y, z] metres from VideoAnalyzer
    danger_level: Optional[str]            # 'low'|'medium'|'high'|'critical'


class RouteWaypoint(TypedDict):
    grid_x: int
    grid_y: int
    zone: str


class EmergencyState(TypedDict):
    # Sensor data
    latest_sensor_payload: dict
    sensor_history: list

    # Fire state
    fire_heatmap: dict
    fire_origin_zone: Optional[str]
    fire_detected_at: Optional[float]

    # Occupant tracking
    occupant_positions: list
    total_registered_occupants: int
    unaccounted_count: int

    # Routing
    safe_routes: dict
    blocked_zones: list

    # Building systems
    hvac_shutdown: bool
    elevators_recalled: bool
    suppression_active: list
    emergency_lighting: bool

    # Status
    threat_level: Literal['none', 'low', 'medium', 'high', 'critical']
    active_alerts: list
    agent_action_log: list
    messages: Annotated[list, add_messages]

    # NL query
    query: Optional[str]
    query_response: Optional[str]

    # Audit
    current_mission_id: Optional[str]
    vision_analysis: Optional[dict]


def initial_state() -> EmergencyState:
    return EmergencyState(
        latest_sensor_payload={},
        sensor_history=[],
        fire_heatmap={},
        fire_origin_zone=None,
        fire_detected_at=None,
        occupant_positions=[],
        total_registered_occupants=4,
        unaccounted_count=4,
        safe_routes={},
        blocked_zones=[],
        hvac_shutdown=False,
        elevators_recalled=False,
        suppression_active=[],
        emergency_lighting=False,
        threat_level='none',
        active_alerts=[],
        agent_action_log=[],
        messages=[],
        query=None,
        query_response=None,
        current_mission_id=None,
        vision_analysis=None,
    )
