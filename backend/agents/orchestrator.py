"""
Orchestrator agent — GPT-4o threat assessment and agent dispatch.
"""
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatOpenAI(
    model=os.getenv('OPENAI_MODEL_ORCHESTRATOR', 'gpt-4o'),
    temperature=0,
)

SYSTEM = '''You are GuardianTwin Orchestrator. Assess fire threat and dispatch agents.
Respond ONLY in valid JSON:
{
  "threat_level": "none|low|medium|high|critical",
  "reasoning": "2-3 sentence explanation",
  "dispatch": ["firesense","tracksense","routepilot","systemctrl","commrelay"]
}
Rules:
- none  = all readings baseline
- low   = smoke_ppm > 50 OR temp_c > 35
- medium = smoke_ppm > 200 OR temp_c > 100
- high  = flame detected OR smoke_ppm > 500
- critical = multi-zone fire
- medium/high/critical → dispatch all 5
- low → dispatch firesense + commrelay
- none → empty dispatch list'''


def orchestrator_node(state: dict) -> dict:
    readings = state.get('latest_sensor_payload', {}).get('readings', [])
    log = list(state.get('agent_action_log', []))

    if not readings:
        return {'agent_action_log': log + ['[Orchestrator] No sensor data']}

    hot = [r for r in readings if r.get('temp_c', 0) > 30 or r.get('smoke_ppm', 0) > 50]
    summary = json.dumps({'hot_zones': hot[:5], 'total_zones': len(readings)})

    try:
        resp = llm.invoke([
            SystemMessage(content=SYSTEM),
            HumanMessage(content=f'Sensor summary: {summary}'),
        ])
        plan = json.loads(resp.content)
    except Exception as e:
        # Preserve last known threat level on failure
        plan = {
            'threat_level': state.get('threat_level', 'low'),
            'dispatch': [],
            'reasoning': f'LLM error: {e}',
        }
        log.append(f'[Orchestrator] LLM timeout, using cached state: {e}')

    log += [
        f'[Orchestrator] Threat={plan["threat_level"]}  Dispatch={plan.get("dispatch", [])}',
        f'[Orchestrator] Reason: {plan.get("reasoning", "")}',
    ]

    return {
        'threat_level': plan.get('threat_level', 'none'),
        'agent_action_log': log,
        'messages': [resp] if 'resp' in dir() else [],
    }
