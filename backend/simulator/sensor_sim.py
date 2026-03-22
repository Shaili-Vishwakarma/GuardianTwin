"""
MQTT sensor simulator — publishes realistic IoT data at 1 Hz.
Fire triggers in zone F3-B at T+30s and spreads to adjacent zones.
"""
import paho.mqtt.client as mqtt
import json
import time
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv
load_dotenv()

BROKER = os.getenv('MQTT_BROKER', 'localhost')
PORT   = int(os.getenv('MQTT_PORT', 1883))
TOPIC  = 'guardiantwin/sensors'
ZONES  = [f'F{f}-{z}' for f in range(1, 4) for z in ['A', 'B', 'C', 'D']]


def baseline(zone: str, t: float) -> dict:
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(random.uniform(5, 15), 2),
        'temp_c':    round(20 + random.uniform(-1, 1), 2),
        'co_ppm':    round(random.uniform(1, 5), 2),
        'humidity':  round(random.uniform(40, 60), 2),
        'flame': False,
    }


def fire(zone: str, t: float, intensity: float) -> dict:
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(15 + intensity * 985, 2),
        'temp_c':    round(20 + intensity * 580, 2),
        'co_ppm':    round(5 + intensity * 195, 2),
        'humidity':  round(60 - intensity * 30, 2),
        'flame': intensity > 0.3,
    }


def run():
    client = mqtt.Client()

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            print(f'[SIM] Connected to MQTT broker at {BROKER}:{PORT}')
        else:
            print(f'[SIM] Connection failed with code {rc}')

    client.on_connect = on_connect
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(BROKER, PORT)
    except Exception as e:
        print(f'[SIM] Could not connect to broker: {e}')
        return

    client.loop_start()
    start = time.time()
    print(f'[SIM] Sensor simulator started. Fire triggers at T+30s on zone F3-B')

    while True:
        t = time.time()
        elapsed = t - start
        readings = []

        for zone in ZONES:
            if elapsed > 30 and zone == 'F3-B':
                readings.append(fire(zone, t, min(1.0, (elapsed - 30) / 60)))
            elif elapsed > 45 and zone == 'F3-A':
                readings.append(fire(zone, t, min(0.6, (elapsed - 45) / 90)))
            elif elapsed > 60 and zone == 'F3-C':
                readings.append(fire(zone, t, min(0.4, (elapsed - 60) / 120)))
            else:
                readings.append(baseline(zone, t))

        payload = json.dumps({'readings': readings, 'sim_time': round(elapsed, 1)})
        client.publish(TOPIC, payload)
        print(f'[SIM] T+{elapsed:.1f}s  {len(readings)} zones published')
        time.sleep(1)


if __name__ == '__main__':
    run()
