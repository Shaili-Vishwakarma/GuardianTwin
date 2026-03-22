"""
Orchestrator agent — threat assessment and agent dispatch.
Uses LLM configured in backend/.env (ollama/fireworks/none).
Rule-based fallback always runs — LLM enriches when available.
"""
import json
import os
import time
from langchain_core.messages import SystemMessage, HumanMessage
from backend.core.llm import get_llm, is_enabled

llm = get_llm(temperature=0)
_llm_enabled = is_enabled()

# Cooldown to avoid hammering the LLM on every 5s tick
_last_llm_call: float = 0.0
_LLM_COOLDOWN: float = 30.0  # seconds between LLM calls

SYSTEM = '''You are GuardianTwin Orchestrator. Assess fire threat and dispatch agents.
Respond ONLY in valid JSON:
{
  "threat_level": "none|low|medium|high|critical",
  "reasoning": "2-3 sentence explanation"
}
Rules:
- none  = all readings baseline
- low   = smoke_ppm > 50 OR temp_c > 35
- medium = smoke_ppm > 200 OR temp_c > 100
- high  = flame detected OR smoke_ppm > 500
- critical = multi-zone fire (2+ zones with flame)'''


def rule_based_threat(readings: list) -> str:
    """Fast deterministic assessment — no API call needed."""
    flame_zones = [r for r in readings if r.get('flame')]
    max_smoke = max((r.get('smoke_ppm', 0) for r in readings), default=0)
    max_temp  = max((r.get('temp_c', 0)   for r in readings), default=0)

    if len(flame_zones) >= 2:
        return 'critical'
    if flame_zones or max_smoke > 500:
        return 'high'
    if max_smoke > 200 or max_temp > 100:
        return 'medium'
    if max_smoke > 50 or max_temp > 35:
        return 'low'
    return 'none'


def orchestrator_node(state: dict) -> dict:
    global _last_llm_call

    readings = state.get('latest_sensor_payload', {}).get('readings', [])
    log = list(state.get('agent_action_log', []))

    if not readings:
        return {'agent_action_log': log + ['[Orchestrator] No sensor data']}

    # Check if all fire zones are extinguished — override sensors
    extinguished = set(state.get('extinguished_zones', []))
    heatmap      = state.get('fire_heatmap', {})
    active_fire_zones = [
        z for z, d in heatmap.items()
        if d.get('fire_prob', 0) > 0.1 and z not in extinguished
    ]
    all_rescued = state.get('unaccounted_count', 1) == 0 and not any(
        o.get('status') == 'at_risk' for o in state.get('occupant_positions', [])
    )

    if not active_fire_zones and extinguished:
        # All fires out — incident over
        threat = 'none'
        log.append('[Orchestrator] ✅ All fires extinguished — threat cleared')
        if all_rescued:
            log.append('[Orchestrator] ✅ All occupants accounted for — ALL CLEAR')
        # Do NOT return early — let the full pipeline run so rescuesim can
        # finish evacuating any at-risk people even after fire is out
        return {
            'threat_level': threat,
            'fire_origin_zone': None if all_rescued else state.get('fire_origin_zone'),
            'agent_action_log': log,
            'messages': [],
        }

    # Rule-based is always the baseline
    threat = rule_based_threat(readings)

    # Log early warning signals even at low threat
    max_smoke = max((r.get('smoke_ppm', 0) for r in readings), default=0)
    max_temp  = max((r.get('temp_c', 0)   for r in readings), default=0)
    hot_zone  = next((r['zone'] for r in readings if r.get('smoke_ppm', 0) == max_smoke), None)
    if threat == 'none' and max_smoke > 20:
        log.append(f'[Orchestrator] 🌫 Elevated smoke in {hot_zone}: {max_smoke:.0f} ppm — monitoring')
    elif threat == 'low':
        log.append(f'[Orchestrator] ⚠ Early warning: {hot_zone} smoke={max_smoke:.0f}ppm temp={max_temp:.0f}°C — standby alert')
    elif threat == 'medium':
        log.append(f'[Orchestrator] 🚨 Pre-fire conditions: {hot_zone} — preparing dispatch')

    # Optionally enrich with LLM (respects cooldown)
    resp = None
    now = time.time()
    if _llm_enabled and llm is not None and (now - _last_llm_call) >= _LLM_COOLDOWN:
        hot = [r for r in readings if r.get('temp_c', 0) > 30 or r.get('smoke_ppm', 0) > 50]
        summary = json.dumps({'hot_zones': hot[:5], 'total_zones': len(readings)})
        try:
            resp = llm.invoke([
                SystemMessage(content=SYSTEM),
                HumanMessage(content=f'Sensor summary: {summary}'),
            ])
            plan = json.loads(resp.content)
            _last_llm_call = now
            threat = plan.get('threat_level', threat)
            log.append(f'[Orchestrator] LLM: {threat} — {plan.get("reasoning", "")[:80]}')
        except Exception as e:
            _last_llm_call = now
            log.append(f'[Orchestrator] LLM error, using rule-based: {e}')
    else:
        log.append(f'[Orchestrator] Rule-based: {threat}')

    log.append(f'[Orchestrator] Threat={threat}')

    return {
        'threat_level': threat,
        'agent_action_log': log,
        'messages': [resp] if resp is not None else [],
    }
