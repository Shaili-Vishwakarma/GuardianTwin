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

    # Rescue agents
    rescue_agents: list

    # Fire suppression
    brigade_zones: list        # zones where fire brigade is actively fighting fire
    fire_brigade: list         # fire brigade unit states
    extinguished_zones: list   # zones confirmed fully extinguished

    # RescueNav 3D simulation bridge
    mission_history: dict      # latest completed NeMo mission result
    mission_stats: dict        # aggregated stats from atlas_learning_db
    nemo_agent_paths: list     # agent paths from last 3D mission

    # Scenario
    scenario: str              # 'fire' or 'attacker'
    attacker_position: dict    # {grid_x, grid_y, zone, floor} when scenario=attacker
    attacker_threat_zones: list  # zones currently threatened by attacker


def initial_state() -> EmergencyState:
    return EmergencyState(
        latest_sensor_payload={},
        sensor_history=[],
        fire_heatmap={},
        fire_origin_zone=None,
        fire_detected_at=None,
        occupant_positions=[],
        total_registered_occupants=15,
        unaccounted_count=15,
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
        rescue_agents=[],
        brigade_zones=[],
        fire_brigade=[],
        extinguished_zones=[],
        mission_history={},
        mission_stats={},
        nemo_agent_paths=[],
        scenario='fire',
        attacker_position={},
        attacker_threat_zones=[],
    )
