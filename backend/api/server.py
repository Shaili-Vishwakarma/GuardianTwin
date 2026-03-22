"""
GuardianTwin FastAPI + WebSocket server.
Receives sensor data via MQTT, runs the LangGraph agent cycle,
and broadcasts state updates to the React frontend over WebSocket.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import asyncio
import json
import threading
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

from backend.core.state import initial_state
from backend.core.graph import run_cycle
from backend.agents.firesense import set_danger_manager
from backend.agents.tracksense import set_video_analyzer

# Validate required env vars at startup
_OPENAI_KEY = os.getenv('OPENAI_API_KEY')
if not _OPENAI_KEY:
    print('[SERVER] ERROR: OPENAI_API_KEY is not set in .env — exiting.')
    sys.exit(1)

app = FastAPI(title='GuardianTwin API')
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

# Optional integrations (graceful fallback if unavailable)
_influx_client = None
_atlas_db = None
_mqtt_connected = False
_influx_connected = False
_mongo_connected = False


# ── InfluxDB (optional) ───────────────────────────────────────────────────────
def _init_influx():
    global _influx_client, _influx_connected
    try:
        from influxdb_client import InfluxDBClient
        from influxdb_client.client.write_api import SYNCHRONOUS
        url   = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        token = os.getenv('INFLUXDB_TOKEN', 'guardiantwin-token')
        org   = os.getenv('INFLUXDB_ORG', 'guardiantwin')
        _influx_client = InfluxDBClient(url=url, token=token, org=org)
        _influx_connected = True
        print('[SERVER] InfluxDB connected')
    except Exception as e:
        print(f'[SERVER] InfluxDB unavailable (continuing without it): {e}')


def _write_influx(payload: dict):
    if not _influx_client or not _influx_connected:
        return
    try:
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        bucket = os.getenv('INFLUXDB_BUCKET', 'sensors')
        org    = os.getenv('INFLUXDB_ORG', 'guardiantwin')
        write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
        for r in payload.get('readings', []):
            p = (
                Point('sensor_reading')
                .tag('zone', r.get('zone', 'unknown'))
                .field('smoke_ppm', float(r.get('smoke_ppm', 0)))
                .field('temp_c',    float(r.get('temp_c', 0)))
                .field('co_ppm',    float(r.get('co_ppm', 0)))
                .field('humidity',  float(r.get('humidity', 0)))
                .field('flame',     int(r.get('flame', False)))
            )
            write_api.write(bucket=bucket, org=org, record=p)
    except Exception as e:
        print(f'[SERVER] InfluxDB write error: {e}')


# ── Atlas DB (optional) ───────────────────────────────────────────────────────
def _init_atlas():
    global _atlas_db, _mongo_connected
    try:
        from atlas_learning_db import AtlasLearningDatabase
        _atlas_db = AtlasLearningDatabase()
        _mongo_connected = True
        print('[SERVER] MongoDB Atlas connected')
    except Exception as e:
        print(f'[SERVER] MongoDB unavailable (continuing without it): {e}')


def _store_cycle(state: dict, latency_ms: float):
    if not _atlas_db:
        return
    try:
        _atlas_db.store_guardian_cycle({
            'cycle_id': state.get('current_mission_id', str(uuid.uuid4())),
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
    except Exception as e:
        print(f'[SERVER] Atlas write error: {e}')


# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def broadcast(state: dict):
    msg = json.dumps({
        'threat_level':       state.get('threat_level', 'none'),
        'fire_heatmap':       state.get('fire_heatmap', {}),
        'occupant_positions': state.get('occupant_positions', []),
        'safe_routes':        state.get('safe_routes', {}),
        'active_alerts':      state.get('active_alerts', []),
        'agent_action_log':   state.get('agent_action_log', [])[-20:],
        'hvac_shutdown':      state.get('hvac_shutdown', False),
        'elevators_recalled': state.get('elevators_recalled', False),
        'emergency_lighting': state.get('emergency_lighting', False),
        'fire_origin_zone':   state.get('fire_origin_zone'),
        'unaccounted_count':  state.get('unaccounted_count', 0),
        'query_response':     state.get('query_response'),
    })
    dead = []
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


# ── MQTT ──────────────────────────────────────────────────────────────────────
def on_mqtt_message(client, userdata, msg):
    global current_state, _mqtt_connected
    try:
        payload = json.loads(msg.payload.decode())
        t0 = time.time()
        with lock:
            current_state['latest_sensor_payload'] = payload
            hist = current_state.get('sensor_history', [])
            current_state['sensor_history'] = (hist + [payload])[-60:]
            current_state = run_cycle(current_state)
        latency_ms = (time.time() - t0) * 1000

        # Fire-and-forget side effects
        threading.Thread(target=_write_influx, args=(payload,), daemon=True).start()
        threading.Thread(target=_store_cycle, args=(current_state, latency_ms), daemon=True).start()

        # Broadcast to WebSocket clients
        asyncio.run(broadcast(current_state))
    except Exception as e:
        print(f'[SERVER] MQTT message error: {e}')


def on_mqtt_connect(client, userdata, flags, rc):
    global _mqtt_connected
    if rc == 0:
        _mqtt_connected = True
        client.subscribe('guardiantwin/sensors')
        print('[SERVER] MQTT connected and subscribed')
    else:
        print(f'[SERVER] MQTT connection failed: rc={rc}')


def start_mqtt():
    broker = os.getenv('MQTT_BROKER', 'localhost')
    port   = int(os.getenv('MQTT_PORT', 1883))
    c = mqtt.Client()
    c.on_message = on_mqtt_message
    c.on_connect = on_mqtt_connect
    c.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        c.connect(broker, port)
        c.loop_forever()
    except Exception as e:
        print(f'[SERVER] MQTT start error: {e}')


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket('/ws')
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    # Send current state immediately on connect
    await broadcast(current_state)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get('type') == 'query':
                with lock:
                    current_state['query'] = msg['text']
                    updated = run_cycle(current_state)
                    current_state.update(updated)
                await broadcast(current_state)
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


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'mqtt': _mqtt_connected,
        'influxdb': _influx_connected,
        'mongodb': _mongo_connected,
    }


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event('startup')
def startup():
    # Initialize optional integrations
    _init_influx()
    _init_atlas()

    # Initialize DangerManager and inject into FireSense
    try:
        from building_navigator import Building3D
        from danger_simulator import DangerManager
        building = Building3D()
        dm = DangerManager(building, scenario='fire')
        set_danger_manager(dm)
        print('[SERVER] DangerManager initialized and injected into FireSense')
    except Exception as e:
        print(f'[SERVER] DangerManager unavailable: {e}')

    # Start MQTT listener in daemon thread
    threading.Thread(target=start_mqtt, daemon=True).start()
    print('[SERVER] Started. Listening for sensor data on MQTT.')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
