"""
CommRelay agent — evacuation alerts and natural language query interface.
"""
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatOpenAI(
    model=os.getenv('OPENAI_MODEL_AGENTS', 'gpt-4o-mini'),
    temperature=0.3,
)

QUERY_SYS = (
    'You are GuardianTwin. Answer operator queries using ONLY the data provided. '
    'Be concise and factual. Building state: {state_summary}'
)


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
        try:
            resp = llm.invoke([
                SystemMessage(content=QUERY_SYS.format(state_summary=summary)),
                HumanMessage(content=query),
            ])
            qresp = resp.content
            log.append(f'[CommRelay] Query answered: {query[:50]}')
        except Exception as e:
            qresp = 'Unable to process query at this time. Please check system status.'
            log.append(f'[CommRelay] Query LLM error: {e}')

    # Generate evacuation alerts for at-risk occupants
    at_risk = [p for p in state.get('occupant_positions', []) if p['status'] == 'at_risk']
    routes = state.get('safe_routes', {})

    if at_risk and state.get('threat_level') in ('high', 'critical'):
        for person in at_risk:
            pid = person['person_id']
            # Avoid duplicate alerts
            if any(a.get('person_id') == pid for a in alerts):
                continue
            route_zones = [w['zone'] for w in routes.get(pid, [])][:3]
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
