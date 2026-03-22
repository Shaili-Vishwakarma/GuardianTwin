# Requirements Document: GuardianTwin Integration

## Overview

GuardianTwin is a multi-agent AIoT emergency response system that extends the existing RescuNav rescue simulation into a live digital twin. It autonomously detects fire, tracks occupants, computes evacuation routes, controls building systems, and answers operator queries in natural language — all in real time.

---

## Requirements

### Requirement 1 — MQTT Sensor Simulation

**User Story:** As a demo operator, I want a sensor simulator that publishes realistic IoT data so the system can run end-to-end without physical hardware.

#### Acceptance Criteria

1. GIVEN the simulator is started, WHEN it runs, THEN it publishes one JSON payload per second to the MQTT topic `guardiantwin/sensors` containing readings for all 12 zones (F1-A through F3-D).
2. GIVEN the simulator has been running for 30 seconds, WHEN zone F3-B is evaluated, THEN its `smoke_ppm`, `temp_c`, `co_ppm`, and `flame` values must reflect an active fire condition.
3. GIVEN a fire is active in F3-B, WHEN 45 seconds have elapsed, THEN zone F3-A must begin showing elevated readings (partial spread).
4. GIVEN the simulator is running, WHEN baseline zones are evaluated, THEN `smoke_ppm` stays between 5–15, `temp_c` between 19–21, and `flame` is `false`.
5. GIVEN the MQTT broker is unavailable, WHEN the simulator starts, THEN it must retry connection and log the failure without crashing.

---

### Requirement 2 — EmergencyState Digital Twin

**User Story:** As a developer, I want a single shared state object that all agents read from and write to, so the building's live condition is always consistent across the system.

#### Acceptance Criteria

1. GIVEN the system starts, WHEN `initial_state()` is called, THEN it returns a valid `EmergencyState` TypedDict with all fields populated to safe defaults (`threat_level='none'`, `hvac_shutdown=False`, etc.).
2. GIVEN an agent updates the state, WHEN the next agent in the graph runs, THEN it receives the updated state including all changes from the previous agent.
3. GIVEN the state is serialized for WebSocket broadcast, WHEN it is deserialized by the React frontend, THEN all fields (`fire_heatmap`, `occupant_positions`, `safe_routes`, `active_alerts`, `agent_action_log`) must be present and valid JSON.
4. GIVEN the existing `OccupantPosition` is populated, WHEN it includes data from `VideoAnalyzer`, THEN `coords_3d` and `danger_level` fields must be populated alongside the standard `grid_x`, `grid_y`, `zone` fields.
5. GIVEN a LangGraph cycle completes, WHEN `current_mission_id` is set, THEN the cycle data must be written to MongoDB via `atlas_learning_db.store_guardian_cycle()`.

---

### Requirement 3 — LangGraph Multi-Agent Orchestration

**User Story:** As a system architect, I want a LangGraph StateGraph that routes sensor data through specialized agents in the correct order, so each agent only runs when needed.

#### Acceptance Criteria

1. GIVEN a sensor payload arrives, WHEN the Orchestrator evaluates it and `threat_level` is `none`, THEN no specialist agents are dispatched and the graph terminates at END.
2. GIVEN `threat_level` is `low`, WHEN the graph routes, THEN only CommRelay is dispatched.
3. GIVEN `threat_level` is `medium`, `high`, or `critical`, WHEN the graph routes, THEN all five specialist agents run in order: FireSense → TrackSense → RoutePilot → SystemCtrl → CommRelay.
4. GIVEN the Orchestrator LLM call fails or times out, WHEN the error is caught, THEN the last known `threat_level` is preserved and the failure is logged to `agent_action_log`.
5. GIVEN the full agent cycle runs, WHEN measured end-to-end, THEN total latency must be under 3 seconds for non-LLM agents and under 15 seconds including LLM calls.

---

### Requirement 4 — FireSense Agent (Fire Spread Prediction)

**User Story:** As an emergency operator, I want the system to predict how fire will spread across zones so I can see which areas will become dangerous before they do.

#### Acceptance Criteria

1. GIVEN sensor readings with `temp_c > 25` or `flame: true` in a zone, WHEN FireSense runs, THEN that zone's `fire_prob` in the heatmap must be greater than 0.
2. GIVEN a zone has `fire_prob > 0.1`, WHEN the cellular automata model runs for one tick, THEN adjacent zones (per `ZONE_ADJACENCY`) must have their `fire_prob` increased by `fire_prob * SPREAD_RATE`.
3. GIVEN the existing `DangerManager` has active fire zones, WHEN FireSense merges the overlay, THEN each zone's `fire_prob` must be `max(ca_prob, danger_manager_level)`.
4. GIVEN zones with `fire_prob >= 0.3`, WHEN FireSense completes, THEN those zones must appear in `blocked_zones`.
5. GIVEN `flame: true` in a sensor reading, WHEN FireSense processes it, THEN that zone's `fire_prob` must be at least 0.9.
6. GIVEN FireSense runs, WHEN measured, THEN the heatmap computation must complete in under 5ms.

---

### Requirement 5 — TrackSense Agent (Occupant Tracking)

**User Story:** As an emergency operator, I want to know where every occupant is and whether they are in danger, so I can prioritize evacuation.

#### Acceptance Criteria

1. GIVEN stub occupant data is loaded, WHEN TrackSense runs, THEN `occupant_positions` must contain all 4 registered occupants with valid `zone`, `grid_x`, `grid_y`, and `status` fields.
2. GIVEN an occupant's zone is in `blocked_zones`, WHEN TrackSense processes them, THEN their `status` must be set to `at_risk`.
3. GIVEN a live `VideoAnalyzer` is injected and `vision_analysis` is present in state, WHEN TrackSense runs, THEN it must use `video_analysis_to_occupants()` instead of the stub file.
4. GIVEN TrackSense completes, WHEN `unaccounted_count` is computed, THEN it must equal `total_registered_occupants` minus the number of located occupants.
5. GIVEN the stub file is missing, WHEN TrackSense runs, THEN it must return an empty occupant list and log `[TrackSense] Stub file not found` without crashing.

---

### Requirement 6 — RoutePilot Agent (Evacuation Route Optimization)

**User Story:** As an emergency operator, I want the system to compute the safest evacuation route for each occupant, automatically avoiding fire zones.

#### Acceptance Criteria

1. GIVEN occupants are located and a fire heatmap exists, WHEN RoutePilot runs, THEN it must return a route for every occupant in `occupant_positions`.
2. GIVEN a zone has `fire_prob = 1.0`, WHEN A* computes a route, THEN no waypoint in the route must pass through that zone.
3. GIVEN the fast grid A* returns no path for an occupant, WHEN RoutePilot falls back, THEN it must attempt `Building3D.find_path()` (NetworkX A*) and log `[RoutePilot] Used Building3D fallback for {pid}`.
4. GIVEN routes are computed, WHEN measured, THEN grid A* on the 20×20 grid must complete in under 50ms for all occupants combined.
5. GIVEN the fire heatmap is updated, WHEN `update_building_from_heatmap()` is called, THEN `Building3D` node danger levels must reflect current `fire_prob` values before `find_path()` is invoked.
6. GIVEN no occupants or no heatmap are present, WHEN RoutePilot runs, THEN it must log `[RoutePilot] Waiting for data` and return without error.

---

### Requirement 7 — SystemCtrl Agent (Building Actuator Control)

**User Story:** As a building manager, I want the system to automatically activate safety systems when a fire is detected, so response happens faster than manual intervention.

#### Acceptance Criteria

1. GIVEN `threat_level` is `medium`, `high`, or `critical`, WHEN SystemCtrl runs for the first time, THEN `hvac_shutdown` must be set to `true` and `[SystemCtrl] HVAC shutdown command sent` must appear in `agent_action_log`.
2. GIVEN `threat_level` is `high` or `critical`, WHEN SystemCtrl runs for the first time, THEN `elevators_recalled` and `emergency_lighting` must both be set to `true`.
3. GIVEN a zone has `fire_prob > 0.6` and is not already in `suppression_active`, WHEN SystemCtrl runs, THEN that zone must be added to `suppression_active` and logged.
4. GIVEN `hvac_shutdown` is already `true`, WHEN SystemCtrl runs again, THEN it must not duplicate the log entry or re-send the command.
5. GIVEN `threat_level` drops to `none` or `low`, WHEN SystemCtrl runs, THEN it must not activate any new systems.

---

### Requirement 8 — CommRelay Agent (Alerts and NL Query)

**User Story:** As an emergency operator, I want to ask the system plain-language questions and receive personalized evacuation alerts, so I can act quickly without reading raw data.

#### Acceptance Criteria

1. GIVEN an occupant has `status='at_risk'` and `threat_level` is `high` or `critical`, WHEN CommRelay runs, THEN a personalized alert must be added to `active_alerts` containing the occupant's ID, their route zones, and a "Do NOT use elevators" instruction.
2. GIVEN a `query` string is set in state, WHEN CommRelay runs, THEN it must call GPT-4o-mini with the current state summary and populate `query_response` with the answer.
3. GIVEN a query is answered, WHEN CommRelay completes, THEN `query` must be reset to `None` to prevent re-processing on the next cycle.
4. GIVEN the LLM call for a query times out, WHEN the error is caught, THEN `query_response` must be set to a fallback message and the failure logged.
5. GIVEN a query is submitted via WebSocket, WHEN measured end-to-end, THEN the response must appear in the dashboard in under 4 seconds.

---

### Requirement 9 — FastAPI + WebSocket Server

**User Story:** As a frontend developer, I want a real-time server that pushes state updates to the dashboard as they happen, so the UI always reflects the current building condition.

#### Acceptance Criteria

1. GIVEN the server starts, WHEN the MQTT broker is available, THEN it must subscribe to `guardiantwin/sensors` and begin processing messages within 2 seconds.
2. GIVEN a sensor payload is received, WHEN the agent cycle completes, THEN the updated state must be broadcast to all connected WebSocket clients within 500ms.
3. GIVEN a WebSocket client sends `{"type": "query", "text": "..."}`, WHEN the server receives it, THEN it must set `state['query']`, run a new agent cycle, and broadcast the result including `query_response`.
4. GIVEN a WebSocket client disconnects, WHEN the next broadcast occurs, THEN the dead client must be silently removed from the client list without crashing.
5. GIVEN `GET /state` is called, WHEN the server responds, THEN it must return the current snapshot of `threat_level`, `fire_heatmap`, `occupant_positions`, `safe_routes`, `active_alerts`, and `agent_action_log`.
6. GIVEN `GET /health` is called, WHEN the server responds, THEN it must return the connection status of MQTT, InfluxDB, and MongoDB.
7. GIVEN all state mutations happen from the MQTT thread, WHEN concurrent access occurs, THEN a `threading.Lock` must guard all reads and writes to `current_state`.

---

### Requirement 10 — React Control Room Dashboard

**User Story:** As an emergency operator, I want a real-time visual dashboard showing the floor plan, fire heatmap, occupant positions, evacuation routes, and live alerts, so I have a complete situational picture at a glance.

#### Acceptance Criteria

1. GIVEN the dashboard loads, WHEN it connects to `ws://localhost:8000/ws`, THEN it must auto-reconnect every 2 seconds if the connection drops.
2. GIVEN `fire_heatmap` data is received, WHEN the FloorPlan renders, THEN each zone must be overlaid with a color from transparent (0% fire) to red (100% fire) proportional to `fire_prob`.
3. GIVEN `occupant_positions` data is received, WHEN the FloorPlan renders, THEN each occupant must appear as a colored dot: red for `at_risk`, green for `safe`, amber for `unknown`.
4. GIVEN `safe_routes` data is received, WHEN the FloorPlan renders, THEN each route must appear as a green dashed polyline from the occupant's position to the nearest exit.
5. GIVEN `active_alerts` data is received, WHEN the alerts panel renders, THEN the 5 most recent alerts must be shown with the person ID highlighted in red.
6. GIVEN `agent_action_log` data is received, WHEN the agent trace panel renders, THEN the 20 most recent log entries must be shown in reverse chronological order.
7. GIVEN the operator types a query and presses Enter or clicks Ask, WHEN the WebSocket message is sent, THEN the `query_response` must appear in the dashboard within 4 seconds.
8. GIVEN `hvac_shutdown` or `elevators_recalled` is `true`, WHEN the header renders, THEN the corresponding status badge must be visible.

---

### Requirement 11 — Adapter Layer (Existing System Integration)

**User Story:** As a developer, I want the existing `Building3D`, `DangerManager`, and `VideoAnalyzer` components to be reused by GuardianTwin without modifying their source files.

#### Acceptance Criteria

1. GIVEN a zone label like `F3-B` and grid coordinates, WHEN `zone_to_position3d()` is called, THEN it must return a valid `Position3D` with correct `x`, `y`, `z`, and `floor` values matching the 20×20 grid layout.
2. GIVEN a `Position3D` from `Building3D`, WHEN `position3d_to_zone()` is called, THEN it must return the correct zone label (e.g. `F2-C`).
3. GIVEN `DangerManager` has active fire zones, WHEN `danger_zones_to_heatmap_overlay()` is called, THEN it must return only fire-type zones (not attacker zones) as a `zone → danger_level` dict.
4. GIVEN a fire heatmap, WHEN `update_building_from_heatmap()` is called, THEN `Building3D` node danger levels must be updated so that `find_path()` avoids high-probability fire zones.
5. GIVEN `VideoAnalyzer` people detection output, WHEN `video_analysis_to_occupants()` is called, THEN pixel bounding boxes must be correctly mapped to `grid_x`, `grid_y`, and zone labels.
6. GIVEN `building_navigator.py`, `danger_simulator.py`, and `main.py` are used by adapters, WHEN the adapters run, THEN those source files must remain unmodified.

---

### Requirement 12 — Infrastructure (Docker)

**User Story:** As a developer, I want MQTT and InfluxDB to start with a single command so the demo environment is reproducible.

#### Acceptance Criteria

1. GIVEN `docker-compose up -d` is run, WHEN both containers start, THEN the MQTT broker must be reachable on port 1883 and InfluxDB on port 8086 within 30 seconds.
2. GIVEN the MQTT broker starts, WHEN `mosquitto.conf` is loaded, THEN anonymous connections must be allowed on port 1883 (TCP) and port 9001 (WebSocket).
3. GIVEN InfluxDB starts, WHEN the environment variables are applied, THEN the `guardiantwin` org, `sensors` bucket, and admin token must be auto-initialized.
4. GIVEN sensor data is written to InfluxDB, WHEN queried, THEN the last 60 seconds of readings must be retrievable per zone.

---

### Requirement 13 — Existing System Preservation

**User Story:** As a developer, I want the existing Flask rescue simulation to keep working unchanged alongside GuardianTwin, so both systems can be demonstrated independently.

#### Acceptance Criteria

1. GIVEN `web_app.py` is started on port 5000, WHEN GuardianTwin's FastAPI server is also running on port 8000, THEN both must operate without port conflicts or shared state corruption.
2. GIVEN `rescue_simulation.py` is run directly, WHEN it executes, THEN it must complete without any import errors caused by new GuardianTwin files.
3. GIVEN `atlas_learning_db.py` is extended with `store_guardian_cycle()`, WHEN existing rescue simulation code calls `store_mission()` or `get_learning_data()`, THEN those methods must behave identically to before.
4. GIVEN `building_navigator.py` and `danger_simulator.py` are shared, WHEN both systems import them, THEN no global state must be shared between the Flask and FastAPI processes.

---

### Requirement 14 — Security and Configuration

**User Story:** As a developer, I want all secrets stored in environment variables and never committed to the repository.

#### Acceptance Criteria

1. GIVEN the project is set up, WHEN `.env` is checked, THEN it must contain `OPENAI_API_KEY`, `MQTT_BROKER`, `MQTT_PORT`, `INFLUXDB_URL`, `INFLUXDB_TOKEN`, and `MONGODB_URI`.
2. GIVEN `.gitignore` is checked, WHEN `.env` is present, THEN it must be listed in `.gitignore` and must not appear in any git commit.
3. GIVEN the system runs on localhost, WHEN any service is accessed, THEN no service must be bound to a public network interface.
4. GIVEN the OpenAI API key is missing from `.env`, WHEN the server starts, THEN it must log a clear error and exit rather than silently failing on the first LLM call.
