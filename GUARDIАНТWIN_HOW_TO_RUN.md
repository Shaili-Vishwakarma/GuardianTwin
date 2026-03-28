# GuardianTwin — How to Run

## Prerequisites
- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- OpenAI API key

## 1. Environment Setup

Copy and fill in your secrets:
```bash
cp backend/.env.example backend/.env
# Edit backend/.env — set OPENAI_API_KEY at minimum
```

## 2. Start Infrastructure (Docker)
```bash
docker-compose up -d
```
This starts:
- Eclipse Mosquitto MQTT broker on port 1883
- InfluxDB on port 8086

## 3. Install Python Dependencies
```bash
pip install -r backend/requirements.txt
# Existing deps (if not already installed):
pip install -r requirements_rescue.txt
```

## 4. Start the Backend API
```bash
cd backend && python api/server.py
```
FastAPI server starts on http://localhost:8000

## 5. Start the Sensor Simulator
```bash
cd backend && python simulator/sensor_sim.py
```
Publishes sensor data every second. Fire triggers at T+30s in zone F3-B.

## 6. Start the React Frontend
```bash
cd frontend && npm install && npm run dev
```
Dashboard opens at http://localhost:5173

## 7. (Optional) Start the Existing Flask UI
```bash
python web_app.py
```
Original rescue simulation UI at http://localhost:5000

---

## Demo Sequence (90 seconds)

| Time | What happens |
|------|-------------|
| T=0s | All zones normal. Threat: NONE. |
| T=30s | Fire triggers in F3-B. Sensor readings spike. |
| T=33s | Orchestrator assesses: Threat=HIGH, dispatches all 5 agents. |
| T=35s | FireSense predicts spread to F3-A. Red heatmap appears. |
| T=37s | TrackSense locates P1 (at risk in F3-B), P2 (at risk in F3-A). |
| T=39s | RoutePilot computes green dashed evacuation routes. |
| T=41s | SystemCtrl: HVAC OFF, Elevators RECALLED. |
| T=43s | CommRelay sends personalized alerts to P1 and P2. |
| T=50s | Type a query: "How many people are unaccounted for?" |
| T=52s | CommRelay answers in under 4 seconds. |

## Backup Queries
- Which zones are currently on fire?
- Is it safe to use the north stairwell?
- What building systems have been activated?
- How long until fire reaches floor 2?
- Who is still unaccounted for?
