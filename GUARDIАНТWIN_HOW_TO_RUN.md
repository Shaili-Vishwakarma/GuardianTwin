# GuardianTwin — How to Run

## Prerequisites

- Python 3.11+
- Node.js 20+
- Fireworks AI API key (free at fireworks.ai) — used by Orchestrator and CommRelay agents
- Ollama (optional, for local LLM) — download at ollama.com

---

## Quick Start — Local Mode (No Docker Required)

This is the recommended way to run for development and demos.

### Step 1 — Environment Setup

```bash
copy backend\.env.example backend\.env
```

Open `backend\.env` and set at minimum:

```
FIREWORKS_API_KEY=your_key_here
LLM_PROVIDER=fireworks
ENABLE_LLM=true
```

To use Ollama instead (fully local, no API key):
```
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:1b
ENABLE_LLM=true
```

To disable LLM entirely (rule-based only, fastest):
```
ENABLE_LLM=false
```

### Step 2 — Install Python Dependencies

```bash
pip install -r backend/requirements.txt
pip install -r requirements_rescue.txt
```

### Step 3 — Install Frontend Dependencies

```bash
cd frontend
npm install
```

### Step 4 — Start the Backend (Terminal 1)

```bash
python backend/api/local_server.py
```

You should see:
```
[SERVER] Local mode started — no Docker needed.
[SERVER] Dashboard: http://localhost:5173
[SERVER] API:       http://localhost:8000
[SIM] Local simulator started.
[SIM] T+0s:  All zones normal — occupants visible
[SIM] T+15s: F3-B smoke rising — early warning
[SIM] T+30s: F3-B ignites — fire spreading via CA model
```

### Step 5 — Start the React Dashboard (Terminal 2)

```bash
cd frontend
npm run dev
```

Open your browser at **http://localhost:5173**

---

## What to Expect on the Dashboard

| Time | What you see |
|------|-------------|
| T=0s | 15 occupants visible as green dots. Threat: NONE. All units standby. |
| T=15s | Agent trace shows smoke rising in F3-B. Early warning logged. |
| T=30s | Fire ignites in F3-B. Heatmap turns red. Threat jumps to HIGH. |
| T=33s | Orchestrator dispatches all agents. HVAC OFF + LIFTS RECALLED badges appear. |
| T=35s | FireSense predicts spread to F3-A and F3-C. Unsafe path warnings logged. |
| T=37s | TrackSense marks P01/P02 as at-risk (red dots). Rescue agents R1/R2/R3 deploy. |
| T=39s | RoutePilot draws green dashed evacuation routes for all occupants. |
| T=43s | CommRelay sends personalized evacuation alerts. |
| T=50s | Sprinklers activate in F3-B after 15s sustained danger. |
| T=60s | Fire brigade FB1/FB2 respond and begin fighting fire. |
| T=90s | Fire extinguished. ALL CLEAR banner appears. |

### Enable Siren Audio

Click the **🔕 Siren** button in the top bar before fire triggers. It turns to **🔔 Armed**. The siren plays automatically for 5 seconds when fire is first detected.

### Scenario Toggle

Use the **🔥 Fire / 🔴 Attacker** toggle in the top bar to switch scenarios:
- **Fire** — sensor-driven fire spread, sprinklers, fire brigade, evacuation routes
- **Attacker** — attacker patrols floors 2-3, threatened zones highlighted in red

### Operator Query

Click **🎙 Query** in the top bar to open the query panel. Type any question and press Enter:

- How many people are trapped?
- Which zones are on fire?
- What building systems have been activated?
- Is it safe to use the north stairwell?
- How long until fire reaches floor 2?
- Who is still unaccounted for?

Responses appear in under 1 second (rule-based engine).

### Mission Panel (3D RescueNav Integration)

Click **📊 Missions** in the top bar to see:
- Total missions run, success rate, best/worst times
- Last mission result (agents alive, rescued, time taken)
- **Run 3D Mission Now** button to manually trigger a `RescueSimulationEngine` mission

The 3D NeMo agent paths appear on the floor plan as thin purple dashed trails after each mission completes. Fire detection automatically triggers a mission in the background.

---

## Docker Mode (with MQTT + InfluxDB)

Use this if you want the full infrastructure stack.

### Prerequisites
- Docker + Docker Compose installed

### Start Infrastructure
```bash
docker-compose up -d
```
Starts:
- Eclipse Mosquitto MQTT broker on port 1883
- InfluxDB on port 8086

### Start Backend (MQTT mode)
```bash
python backend/api/server.py
```

### Start Sensor Simulator
```bash
python backend/simulator/sensor_sim.py
```

### Start Frontend
```bash
cd frontend && npm run dev
```

---

## Run Tests

```bash
pip install pytest hypothesis
python -m pytest backend/tests/ -v
```

Expected: **27 passed**

---

## Optional — Existing Flask Rescue Simulation

The original RescuNav simulation still works alongside GuardianTwin:

```bash
python web_app.py
```

Opens at **http://localhost:5000** — completely independent, no port conflicts.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `FIREWORKS_API_KEY not set` | Check `backend/.env` has the key, or set `ENABLE_LLM=false` |
| `ModuleNotFoundError: langgraph` | Run `pip install -r backend/requirements.txt` |
| Frontend blank / no data | Make sure backend is running on port 8000 first |
| Siren not playing | Click the `🔕 Siren` button in the top bar to arm it before fire triggers |
| Ollama not responding | Run `ollama pull llama3.2:1b` then restart the backend |
| Building3D slow to init | Normal — takes ~2s on first cycle, cached after that |
