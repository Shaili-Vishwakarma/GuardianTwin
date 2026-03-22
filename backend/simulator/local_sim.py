"""
Local sensor simulator — no MQTT broker required.
Publishes directly to an in-process queue consumed by the server.

Timeline:
  T+0s:   All zones baseline (people visible, status=safe)
  T+15s:  F3-B shows rising smoke (early warning)
  T+25s:  F3-B smoke critical, temp rising (pre-fire alert)
  T+30s:  F3-B ignites (flame=True), fire spreads via CA model only
"""
import json
import time
import random
import threading

ZONES = [f'F{f}-{z}' for f in range(1, 4) for z in ['A', 'B', 'C', 'D']]

_message_queue = None


def set_queue(q):
    global _message_queue
    _message_queue = q


def baseline(zone: str, t: float) -> dict:
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(random.uniform(5, 15), 2),
        'temp_c':    round(20 + random.uniform(-1, 1), 2),
        'co_ppm':    round(random.uniform(1, 5), 2),
        'humidity':  round(random.uniform(40, 60), 2),
        'flame': False,
    }


def pre_fire(zone: str, t: float, intensity: float) -> dict:
    """Rising smoke/temp before ignition — early warning phase."""
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(15 + intensity * 185, 2),   # 15→200 ppm
        'temp_c':    round(20 + intensity * 30, 2),     # 20→50°C
        'co_ppm':    round(5 + intensity * 20, 2),
        'humidity':  round(60 - intensity * 10, 2),
        'flame': False,
    }


def fire(zone: str, t: float, intensity: float) -> dict:
    """Active fire — intensity 0→1 over 60s."""
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(200 + intensity * 800, 2),
        'temp_c':    round(50 + intensity * 550, 2),
        'co_ppm':    round(25 + intensity * 175, 2),
        'humidity':  round(50 - intensity * 30, 2),
        'flame': intensity > 0.3,
    }


def run(queue):
    set_queue(queue)
    start = time.time()
    print('[SIM] Local simulator started.')
    print('[SIM] T+0s:  All zones normal — occupants visible')
    print('[SIM] T+15s: F3-B smoke rising — early warning')
    print('[SIM] T+25s: F3-B pre-ignition — critical smoke')
    print('[SIM] T+30s: F3-B ignites — fire spreading via CA model')

    while True:
        t = time.time()
        elapsed = t - start
        readings = []

        for zone in ZONES:
            if zone == 'F3-B':
                if elapsed > 30:
                    # Active fire — grows over 60s
                    readings.append(fire(zone, t, min(1.0, (elapsed - 30) / 60)))
                elif elapsed > 15:
                    # Pre-fire: rising smoke/temp (15s window before ignition)
                    pre_intensity = (elapsed - 15) / 15.0
                    readings.append(pre_fire(zone, t, pre_intensity))
                else:
                    readings.append(baseline(zone, t))
            else:
                readings.append(baseline(zone, t))

        payload = {'readings': readings, 'sim_time': round(elapsed, 1)}
        queue.put(payload)

        # Descriptive sim log
        if elapsed < 15:
            print(f'[SIM] T+{elapsed:.0f}s  Normal operations — all zones clear')
        elif elapsed < 30:
            smoke = next(r['smoke_ppm'] for r in readings if r['zone'] == 'F3-B')
            print(f'[SIM] T+{elapsed:.0f}s  ⚠ F3-B smoke rising: {smoke:.0f} ppm')
        else:
            temp = next(r['temp_c'] for r in readings if r['zone'] == 'F3-B')
            flame = next(r['flame'] for r in readings if r['zone'] == 'F3-B')
            print(f'[SIM] T+{elapsed:.0f}s  🔥 F3-B fire: {temp:.0f}°C flame={flame}')

        time.sleep(5)


def start_in_thread(queue):
    t = threading.Thread(target=run, args=(queue,), daemon=True)
    t.start()
    return t
