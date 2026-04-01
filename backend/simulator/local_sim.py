"""
Local sensor simulator — no MQTT broker required.
Publishes directly to an in-process queue consumed by the server.

Fire scenario timeline:
  T+0s:   All zones baseline
  T+15s:  F3-B shows rising smoke (early warning)
  T+30s:  F3-B ignites, fire spreads via CA model

Attacker scenario:
  All zones stay at baseline — no fire sensor data.
  The attacker position comes from AttackerSimulator (danger_simulator.py).
"""
import time
import random
import threading

ZONES = [f'F{f}-{z}' for f in range(1, 4) for z in ['A', 'B', 'C', 'D']]

_message_queue = None
# Stop event — set to stop the current simulator thread
_stop_event: threading.Event = threading.Event()


def set_queue(q):
    global _message_queue
    _message_queue = q


def stop():
    """Signal the running simulator thread to stop."""
    _stop_event.set()


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
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(15 + intensity * 185, 2),
        'temp_c':    round(20 + intensity * 30, 2),
        'co_ppm':    round(5 + intensity * 20, 2),
        'humidity':  round(60 - intensity * 10, 2),
        'flame': False,
    }


def fire(zone: str, t: float, intensity: float) -> dict:
    return {
        'zone': zone, 'timestamp': t,
        'smoke_ppm': round(200 + intensity * 800, 2),
        'temp_c':    round(50 + intensity * 550, 2),
        'co_ppm':    round(25 + intensity * 175, 2),
        'humidity':  round(50 - intensity * 30, 2),
        'flame': intensity > 0.3,
    }


def run_fire(queue, stop_event: threading.Event):
    """Fire scenario — F3-B ignites at T+30s."""
    set_queue(queue)
    start = time.time()
    print('[SIM] Fire scenario started.')
    print('[SIM] T+0s:  All zones normal — occupants visible')
    print('[SIM] T+15s: F3-B smoke rising — early warning')
    print('[SIM] T+30s: F3-B ignites — fire spreading via CA model')

    while not stop_event.is_set():
        t = time.time()
        elapsed = t - start
        readings = []

        for zone in ZONES:
            if zone == 'F3-B':
                if elapsed > 30:
                    readings.append(fire(zone, t, min(1.0, (elapsed - 30) / 60)))
                elif elapsed > 15:
                    readings.append(pre_fire(zone, t, (elapsed - 15) / 15.0))
                else:
                    readings.append(baseline(zone, t))
            else:
                readings.append(baseline(zone, t))

        payload = {'readings': readings, 'sim_time': round(elapsed, 1)}
        queue.put(payload)

        if elapsed < 15:
            print(f'[SIM] T+{elapsed:.0f}s  Normal — all zones clear')
        elif elapsed < 30:
            smoke = next(r['smoke_ppm'] for r in readings if r['zone'] == 'F3-B')
            print(f'[SIM] T+{elapsed:.0f}s  ⚠ F3-B smoke: {smoke:.0f} ppm')
        else:
            temp = next(r['temp_c'] for r in readings if r['zone'] == 'F3-B')
            flame = next(r['flame'] for r in readings if r['zone'] == 'F3-B')
            print(f'[SIM] T+{elapsed:.0f}s  🔥 F3-B: {temp:.0f}°C flame={flame}')

        # Sleep in small increments so stop_event is checked promptly
        for _ in range(50):
            if stop_event.is_set():
                break
            time.sleep(0.1)

    print('[SIM] Fire simulator stopped.')


def run_attacker(queue, stop_event: threading.Event):
    """Attacker scenario — all zones stay at baseline (no fire)."""
    set_queue(queue)
    start = time.time()
    print('[SIM] Attacker scenario started.')
    print('[SIM] T+0s:  Building secure — all sensors normal')
    print('[SIM] T+5s:  Attacker detected — beginning patrol on floors 2-3')

    while not stop_event.is_set():
        t = time.time()
        elapsed = t - start
        readings = [baseline(zone, t) for zone in ZONES]
        payload = {'readings': readings, 'sim_time': round(elapsed, 1)}
        queue.put(payload)

        if elapsed < 5:
            print(f'[SIM] T+{elapsed:.0f}s  🔒 Building secure — monitoring')
        else:
            print(f'[SIM] T+{elapsed:.0f}s  🔴 Attacker active — tracking position')

        for _ in range(50):
            if stop_event.is_set():
                break
            time.sleep(0.1)

    print('[SIM] Attacker simulator stopped.')


def run(queue, scenario: str = 'fire', stop_event: threading.Event = None):
    """Entry point — routes to correct scenario runner."""
    if stop_event is None:
        stop_event = threading.Event()
    if scenario == 'attacker':
        run_attacker(queue, stop_event)
    else:
        run_fire(queue, stop_event)


def start_in_thread(queue, scenario: str = 'fire') -> threading.Event:
    """Start simulator in background thread. Returns stop_event to kill it."""
    stop_event = threading.Event()
    t = threading.Thread(target=run, args=(queue, scenario, stop_event), daemon=True)
    t.start()
    return stop_event
