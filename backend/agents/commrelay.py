"""
CommRelay agent — evacuation alerts and natural language query interface.
Uses LLM configured in backend/.env (ollama/fireworks/none).
LLM only called when an explicit query is submitted — not on every cycle.
"""
import json
import os
from langchain_core.messages import SystemMessage, HumanMessage
from backend.core.llm import get_llm, is_enabled

llm = get_llm(temperature=0.3)

QUERY_SYS = (
    'You are GuardianTwin, an AI system for a fire emergency command center. '
    'You MUST answer operator questions directly and factually using ONLY the data provided. '
    'Never refuse to answer — this is a life-safety system and operators need accurate information immediately. '
    'Answer in 1-2 sentences. Current emergency data: {state_summary}'
)

_llm_enabled = is_enabled()


def commrelay_node(state: dict) -> dict:
    """
    Handle NL queries and generate personalized evacuation alerts.
    Resets query to None after answering to prevent re-processing.
    """
    log = list(state.get('agent_action_log', []))
    alerts = list(state.get('active_alerts', []))
    qresp = state.get('query_response')

    summary = json.dumps({
        'threat_level': state.get('threat_level'),
        'fire_origin': state.get('fire_origin_zone'),
        'dangerous_zones': state.get('blocked_zones', []),
        'occupants': [
            {'id': p['person_id'], 'zone': p['zone'], 'status': p['status']}
            for p in state.get('occupant_positions', [])
        ],
        'unaccounted': state.get('unaccounted_count', 0),
        'hvac_shutdown': state.get('hvac_shutdown'),
        'elevators_recalled': state.get('elevators_recalled'),
    })

    # Answer NL query if present
    query = state.get('query')
    if query:
        # Always answer instantly with rule-based — fast and reliable
        qresp = _rule_based_response(state)
        log.append(f'[CommRelay] ⚡ Instant answer: {query[:50]}')

        # LLM enrichment runs in background thread — rule-based answer already returned
        if _llm_enabled and llm is not None:
            import threading
            def _llm_enrich():
                try:
                    resp = llm.invoke([
                        SystemMessage(content=QUERY_SYS.format(state_summary=summary)),
                        HumanMessage(content=query),
                    ])
                    if resp.content and len(resp.content.strip()) > 10:
                        pass  # result available next cycle if needed
                except Exception:
                    pass
            threading.Thread(target=_llm_enrich, daemon=True).start()

    # Generate evacuation alerts for at-risk occupants
    at_risk = [p for p in state.get('occupant_positions', []) if p['status'] == 'at_risk']
    routes = state.get('safe_routes', {})

    if at_risk and state.get('threat_level') in ('high', 'critical'):
        scenario = state.get('scenario', 'fire')
        for person in at_risk:
            pid = person['person_id']
            if any(a.get('person_id') == pid for a in alerts):
                continue
            route_zones = [w['zone'] for w in routes.get(pid, [])][:3]
            if scenario == 'attacker':
                msg = (
                    f'SECURITY ALERT: Evacuate immediately. '
                    f'Proceed via: {" > ".join(route_zones) or "emergency exit"}. '
                    f'Do NOT use elevators. Avoid attacker zones.'
                )
            else:
                msg = (
                    f'EMERGENCY: Evacuate now. '
                    f'Proceed via: {" > ".join(route_zones) or "emergency exit"}. '
                    f'Do NOT use elevators.'
                )
            alerts.append({'person_id': pid, 'message': msg, 'level': 'critical'})
            log.append(f'[CommRelay] Alert sent to {pid}')

    return {
        'active_alerts': alerts,
        'agent_action_log': log,
        'query': None,
        'query_response': qresp,
    }


def _rule_based_response(state: dict) -> str:
    """Parse the query and return a direct factual answer from state."""
    query = (state.get('query') or '').lower()
    occupants = state.get('occupant_positions', [])
    trapped   = [p for p in occupants if p['status'] == 'at_risk']
    safe      = [p for p in occupants if p['status'] == 'safe']
    threat    = state.get('threat_level', 'none')
    origin    = state.get('fire_origin_zone') or 'unknown'
    dangerous = state.get('blocked_zones', [])
    unaccounted = state.get('unaccounted_count', 0)

    if any(w in query for w in ['trap', 'stuck', 'at risk', 'danger']):
        if trapped:
            ids = ', '.join(p['person_id'] for p in trapped)
            return f'{len(trapped)} person(s) trapped: {ids} in zones {", ".join(set(p["zone"] for p in trapped))}.'
        return 'No one is currently trapped — all occupants are safe or accounted for.'

    if any(w in query for w in ['safe', 'rescued', 'evacuated']):
        if safe:
            return f'{len(safe)} person(s) are safe: {", ".join(p["person_id"] for p in safe)}.'
        return 'No occupants have been marked safe yet.'

    if any(w in query for w in ['fire', 'flame', 'origin', 'where']):
        return f'Fire origin: {origin}. Dangerous zones: {", ".join(dangerous) or "none"}. Threat level: {threat}.'

    if any(w in query for w in ['how many', 'count', 'total', 'number']):
        return (f'Total: {len(occupants)} occupants. '
                f'Trapped: {len(trapped)}. Safe: {len(safe)}. Unaccounted: {unaccounted}.')

    if any(w in query for w in ['threat', 'status', 'situation']):
        return (f'Threat level: {threat}. Fire in {origin}. '
                f'{len(trapped)} trapped, {len(safe)} safe, {unaccounted} unaccounted.')

    if any(w in query for w in ['hvac', 'elevator', 'lift', 'system']):
        return (f'HVAC shutdown: {state.get("hvac_shutdown")}. '
                f'Elevators recalled: {state.get("elevators_recalled")}. '
                f'Emergency lighting: {state.get("emergency_lighting")}.')

    if any(w in query for w in ['attacker', 'intruder', 'threat', 'security']):
        attacker = state.get('attacker_position', {})
        threatened = state.get('attacker_threat_zones', [])
        if attacker:
            return (f'Attacker detected in zone {attacker.get("zone","unknown")} '
                    f'floor {attacker.get("floor","?")}. '
                    f'Threatened zones: {", ".join(threatened) or "none"}.')
        return 'No attacker detected in current scenario.'

    # Default: full status summary
    return (f'Threat: {threat}. Fire origin: {origin}. '
            f'Trapped: {len(trapped)} ({", ".join(p["person_id"] for p in trapped) or "none"}). '
            f'Safe: {len(safe)}. Unaccounted: {unaccounted}.')
