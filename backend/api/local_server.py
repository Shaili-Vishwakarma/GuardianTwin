"""
GuardianTwin — LOCAL mode server (no Docker, no MQTT broker required).
Runs the sensor simulator in-process via a queue.
Usage: python backend/api/local_server.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import asyncio
import json
import queue
import threading
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from backend.core.state import initial_state
from backend.core.graph import run_cycle
from backend.agents.firesense import set_danger_manager
from backend.agents.attackersense import set_attacker_sim
from backend.agents.rescuenav_bridge import set_db as set_bridge_db, start_mission

# Validate LLM config — only enforce API key for cloud providers
_provider = os.getenv('LLM_PROVIDER', 'none').lower()
_llm_enabled = os.getenv('ENABLE_LLM', 'false').lower() == 'true'

if _llm_enabled and _provider == 'fireworks' and not os.getenv('FIREWORKS_API_KEY'):
    print('[SERVER] ERROR: LLM_PROVIDER=fireworks but FIREWORKS_API_KEY not set — exiting.')
    sys.exit(1)

if _llm_enabled and _provider == 'ollama':
    print('[SERVER] LLM: Ollama (local) — no API key required')
elif _llm_enabled and _provider == 'fireworks':
    print('[SERVER] LLM: Fireworks AI (cloud)')
else:
    print('[SERVER] LLM: disabled — rule-based mode')

app = FastAPI(title='GuardianTwin Local')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# ── Global state ──────────────────────────────────────────────────────────────
current_state = initial_state()
clients: list[WebSocket] = []
lock = threading.Lock()
sensor_queue: queue.Queue = queue.Queue()

# ── Log buffer — captures all backend print output ────────────────────────────
import io, sys as _sys

_log_buffer: list[str] = []
_log_clients: list[asyncio.Queue] = []
_MAX_LOG_LINES = 500

class _LogCapture(io.TextIOBase):
    """Tee stdout to both original stdout and log buffer."""
    def __init__(self, original):
        self._orig = original

    def write(self, s):
        if s and s.strip():
            _log_buffer.append(s.rstrip())
            if len(_log_buffer) > _MAX_LOG_LINES:
                _log_buffer.pop(0)
            for q in list(_log_clients):
                try:
                    q.put_nowait(s.rstrip())
                except Exception:
                    pass
        self._orig.write(s)
        return len(s)

    def flush(self):
        self._orig.flush()

_sys.stdout = _LogCapture(_sys.stdout)

# ── Optional Atlas DB ─────────────────────────────────────────────────────────
_atlas_db = None
_mongo_connected = False


def _init_atlas():
    global _atlas_db, _mongo_connected
    try:
        from atlas_learning_db import AtlasLearningDatabase
        _atlas_db = AtlasLearningDatabase()
        _mongo_connected = True
        print('[SERVER] MongoDB Atlas connected')
    except Exception as e:
        print(f'[SERVER] MongoDB unavailable (skipping): {e}')


def _store_cycle(state: dict, latency_ms: float):
    if not _atlas_db:
        return
    try:
        _atlas_db.store_guardian_cycle({
            'cycle_id': str(uuid.uuid4()),
            'timestamp': time.time(),
            'threat_level': state.get('threat_level'),
            'fire_origin_zone': state.get('fire_origin_zone'),
            'blocked_zones': state.get('blocked_zones', []),
            'occupant_count': len(state.get('occupant_positions', [])),
            'unaccounted_count': state.get('unaccounted_count', 0),
            'routes_computed': len(state.get('safe_routes', {})),
            'hvac_shutdown': state.get('hvac_shutdown', False),
            'elevators_recalled': state.get('elevators_recalled', False),
            'agent_action_log': state.get('agent_action_log', [])[-10:],
            'cycle_latency_ms': latency_ms,
        })
    except Exception:
        pass


# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def broadcast(state: dict):
    msg = json.dumps({
        'threat_level':         state.get('threat_level', 'none'),
        'fire_heatmap':         state.get('fire_heatmap', {}),
        'occupant_positions':   state.get('occupant_positions', []),
        'safe_routes':          state.get('safe_routes', {}),
        'active_alerts':        state.get('active_alerts', []),
        'agent_action_log':     state.get('agent_action_log', [])[-20:],
        'hvac_shutdown':        state.get('hvac_shutdown', False),
        'elevators_recalled':   state.get('elevators_recalled', False),
        'emergency_lighting':   state.get('emergency_lighting', False),
        'fire_origin_zone':     state.get('fire_origin_zone'),
        'unaccounted_count':    state.get('unaccounted_count', 0),
        'query_response':       state.get('query_response'),
        'suppression_active':   state.get('suppression_active', []),
        'rescue_agents':        state.get('rescue_agents', []),
        'fire_brigade':         state.get('fire_brigade', []),
        'brigade_zones':        state.get('brigade_zones', []),
        'extinguished_zones':   state.get('extinguished_zones', []),
        # New fields
        'scenario':             state.get('scenario', 'fire'),
        'attacker_position':    state.get('attacker_position', {}),
        'attacker_threat_zones': state.get('attacker_threat_zones', []),
        'mission_history':      state.get('mission_history', {}),
        'mission_stats':        state.get('mission_stats', {}),
        'nemo_agent_paths':     state.get('nemo_agent_paths', []),
    })
    dead = []
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


# ── Queue consumer — runs in background thread ────────────────────────────────
def consume_queue(loop: asyncio.AbstractEventLoop):
    global current_state
    while True:
        try:
            payload = sensor_queue.get(timeout=1)
            # Only process if simulation has been started by user
            if not _sim_started:
                continue
            t0 = time.time()
            with lock:
                current_state['latest_sensor_payload'] = payload
                hist = current_state.get('sensor_history', [])
                current_state['sensor_history'] = (hist + [payload])[-60:]
                current_state = run_cycle(current_state)
            latency_ms = (time.time() - t0) * 1000
            print(f'[SERVER] Cycle done in {latency_ms:.0f}ms  threat={current_state.get("threat_level")}')
            threading.Thread(target=_store_cycle, args=(current_state, latency_ms), daemon=True).start()
            # Schedule broadcast on the event loop
            asyncio.run_coroutine_threadsafe(broadcast(current_state), loop)
        except queue.Empty:
            continue
        except Exception as e:
            print(f'[SERVER] Cycle error: {e}')


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket('/ws')
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    await broadcast(current_state)  # send current state immediately
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get('type') == 'query':
                # Run in thread pool so WebSocket stays responsive
                loop = asyncio.get_event_loop()
                def handle_query():
                    global current_state
                    with lock:
                        current_state['query'] = msg['text']
                        updated = run_cycle(current_state)
                        current_state.update(updated)
                    asyncio.run_coroutine_threadsafe(broadcast(current_state), loop)
                threading.Thread(target=handle_query, daemon=True).start()
    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)


# ── REST endpoints ────────────────────────────────────────────────────────────
@app.get('/state')
def get_state():
    with lock:
        return {k: current_state.get(k) for k in [
            'threat_level', 'fire_heatmap', 'occupant_positions',
            'safe_routes', 'active_alerts', 'agent_action_log',
        ]}


@app.get('/missions')
def get_missions():
    """Return mission history and learning stats from atlas_learning_db."""
    with lock:
        return {
            'mission_history': current_state.get('mission_history', {}),
            'mission_stats':   current_state.get('mission_stats', {}),
            'nemo_agent_paths': current_state.get('nemo_agent_paths', []),
        }


class ScenarioRequest(BaseModel):
    scenario: str  # 'fire' or 'attacker'


@app.post('/scenario')
def set_scenario(req: ScenarioRequest):
    """Switch between fire and attacker scenarios."""
    global current_state
    if req.scenario not in ('fire', 'attacker'):
        return {'error': 'scenario must be fire or attacker'}
    with lock:
        current_state['scenario'] = req.scenario
        # Reset fire/attacker state when switching
        current_state['fire_heatmap'] = {}
        current_state['blocked_zones'] = []
        current_state['fire_origin_zone'] = None
        current_state['fire_detected_at'] = None
        current_state['attacker_position'] = {}
        current_state['attacker_threat_zones'] = []
        current_state['threat_level'] = 'none'
    print(f'[SERVER] Scenario switched to: {req.scenario}')
    return {'scenario': req.scenario}


@app.post('/trigger_mission')
def trigger_mission():
    """Manually trigger a RescueNav 3D simulation mission."""
    from backend.agents.rescuenav_bridge import start_mission
    from backend.agents import rescuenav_bridge as _rb
    if _rb._mission_running:
        return {'status': 'already_running', 'message': 'A mission is already in progress'}
    scenario = current_state.get('scenario', 'fire')
    start_mission(scenario=scenario, num_agents=3, db=_atlas_db)
    return {'status': 'started', 'scenario': scenario}


@app.get('/mission_status')
def mission_status():
    """Check if a 3D mission is currently running."""
    from backend.agents import rescuenav_bridge as _rb
    return {
        'running': _rb._mission_running,
        'count': _rb._mission_count,
    }


# ── Simulation control ────────────────────────────────────────────────────────
_sim_started = False
_sim_thread = None
_sim_stop_event = None  # threading.Event to stop the current simulator


@app.post('/reset')
def reset_simulation():
    """Reset all state — called when user clicks Home to start fresh."""
    global _sim_started, current_state, _sim_thread, _sim_stop_event
    # Stop the running simulator thread first
    if _sim_stop_event is not None:
        _sim_stop_event.set()
        _sim_stop_event = None
    with lock:
        # Clear the sensor queue so old readings don't bleed into new sim
        while not sensor_queue.empty():
            try:
                sensor_queue.get_nowait()
            except Exception:
                pass
        # Reset to clean initial state
        current_state = initial_state()
        _sim_started = False
        _sim_thread = None
    # Clear log buffer
    _log_buffer.clear()
    # Reset agent module-level state
    try:
        from backend.agents import tracksense as _ts
        _ts._status_memory.clear()
        _ts._smoke_history.clear()
    except Exception:
        pass
    try:
        from backend.agents import rescuesim as _rs
        _rs._initialized = False
        _rs.rescued_people.clear()
    except Exception:
        pass
    try:
        from backend.agents import firebrigade as _fb
        _fb._initialized = False
        _fb.extinguished_zones.clear()
    except Exception:
        pass
    try:
        from backend.agents import attackersense as _as
        _as._last_update = 0.0
    except Exception:
        pass
    try:
        from backend.agents import systemctrl as _sc
        _sc._zone_danger_since.clear()
    except Exception:
        pass
    print('[SERVER] Simulation reset — ready for new scenario')
    return {'status': 'reset'}


class StartRequest(BaseModel):
    scenario: str = 'fire'  # 'fire' or 'attacker'


@app.post('/start_simulation')
def start_simulation(req: StartRequest = None):
    """Start the sensor simulator with chosen scenario."""
    global _sim_started, current_state
    if _sim_started:
        return {'status': 'already_running', 'scenario': current_state.get('scenario')}
    scenario = (req.scenario if req else 'fire')
    if scenario not in ('fire', 'attacker'):
        scenario = 'fire'
    with lock:
        current_state['scenario'] = scenario
    from backend.simulator.local_sim import start_in_thread
    _sim_stop_event = start_in_thread(sensor_queue, scenario)
    _sim_started = True
    print(f'[SERVER] Simulation started — scenario: {scenario}')

    # Immediately inject a baseline payload so the dashboard shows data right away
    import threading as _t
    def _inject_initial():
        import time as _time
        import random as _random
        _time.sleep(0.5)  # let the consumer thread start
        zones = [f'F{f}-{z}' for f in range(1, 4) for z in ['A', 'B', 'C', 'D']]
        readings = [{
            'zone': z, 'timestamp': _time.time(),
            'smoke_ppm': round(_random.uniform(5, 15), 2),
            'temp_c': round(20 + _random.uniform(-1, 1), 2),
            'co_ppm': round(_random.uniform(1, 5), 2),
            'humidity': round(_random.uniform(40, 60), 2),
            'flame': False,
        } for z in zones]
        sensor_queue.put({'readings': readings, 'sim_time': 0.0})
        print('[SERVER] Initial baseline payload injected')
    _t.Thread(target=_inject_initial, daemon=True).start()

    return {'status': 'started', 'scenario': scenario}


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'mode': 'local (no Docker)',
        'mongodb': _mongo_connected,
        'scenario': current_state.get('scenario', 'fire'),
    }


class QueryRequest(BaseModel):
    text: str


@app.post('/query')
def instant_query(req: QueryRequest):
    """Answer operator queries instantly using rule-based engine — no graph cycle needed."""
    from backend.agents.commrelay import _rule_based_response
    with lock:
        state_snapshot = dict(current_state)
        state_snapshot['query'] = req.text
    answer = _rule_based_response(state_snapshot)
    print(f'[CommRelay] ⚡ Instant /query: {req.text[:60]}')
    return {'response': answer}


@app.get('/logs/history')
def logs_history():
    """Return buffered log lines as JSON."""
    return {'lines': list(_log_buffer)}


@app.get('/logs/stream')
async def logs_stream():
    """SSE stream — pushes new log lines as they arrive."""
    q: asyncio.Queue = asyncio.Queue()
    _log_clients.append(q)

    async def event_gen():
        # Send existing buffer first
        for line in list(_log_buffer):
            yield f'data: {line}\n\n'
        try:
            while True:
                line = await q.get()
                yield f'data: {line}\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            if q in _log_clients:
                _log_clients.remove(q)

    return StreamingResponse(
        event_gen(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event('startup')
def startup():
    _init_atlas()

    # Inject bridge db reference
    set_bridge_db(_atlas_db)

    # Inject DangerManager into FireSense (fire scenario)
    _shared_building = None
    try:
        from building_navigator import Building3D
        from danger_simulator import DangerManager
        _shared_building = Building3D()
        dm_fire = DangerManager(_shared_building, scenario='fire')
        set_danger_manager(dm_fire)
        print('[SERVER] DangerManager (fire) injected into FireSense')
    except Exception as e:
        print(f'[SERVER] DangerManager unavailable: {e}')

    # Inject AttackerSimulator into AttackerSense (attacker scenario)
    try:
        from building_navigator import Building3D
        from danger_simulator import DangerManager
        building_a = _shared_building or Building3D()
        dm_attacker = DangerManager(building_a, scenario='attacker')
        set_attacker_sim(dm_attacker.attacker_sim)
        print('[SERVER] AttackerSimulator injected into AttackerSense')
    except Exception as e:
        print(f'[SERVER] AttackerSimulator unavailable: {e}')

    # Inject VideoAnalyzer if VIDEO_PATH is set
    video_path = os.getenv('VIDEO_PATH', '')
    if video_path and os.path.exists(video_path):
        try:
            from main import VideoAnalyzer
            from backend.agents.tracksense import set_video_analyzer
            va = VideoAnalyzer()
            set_video_analyzer(va)
            print(f'[SERVER] VideoAnalyzer injected — using {video_path}')
        except Exception as e:
            print(f'[SERVER] VideoAnalyzer unavailable: {e}')
    else:
        print('[SERVER] VIDEO_PATH not set — using stub occupant data')

    # NOTE: Simulator is NOT auto-started — user clicks Start on dashboard
    # start_in_thread(sensor_queue)  ← moved to /start_simulation endpoint

    # Start queue consumer thread (needs the event loop)
    loop = asyncio.get_event_loop()
    threading.Thread(target=consume_queue, args=(loop,), daemon=True).start()

    print('[SERVER] Local mode started — no Docker needed.')
    print('[SERVER] Dashboard: http://localhost:5173')
    print('[SERVER] API:       http://localhost:8000')
    print('[SERVER] Click START on the dashboard to begin simulation.')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
