"""
LangGraph StateGraph assembly — wires all agent nodes.

Routing:
  - ALWAYS: orchestrator → [firesense OR attackersense] → tracksense
  - threat=none, no query: tracksense → rescuenav_bridge → END
  - threat=low or query:   tracksense → routepilot → commrelay → rescuenav_bridge → END
  - threat>=medium or at_risk: full pipeline including rescue + brigade + rescuenav_bridge
"""
from langgraph.graph import StateGraph, END
from backend.core.state import EmergencyState, initial_state
from backend.agents.orchestrator import orchestrator_node
from backend.agents.firesense import firesense_node
from backend.agents.attackersense import attackersense_node
from backend.agents.tracksense import tracksense_node
from backend.agents.routepilot import routepilot_node
from backend.agents.systemctrl import systemctrl_node
from backend.agents.commrelay import commrelay_node
from backend.agents.rescuesim import rescuesim_node
from backend.agents.firebrigade import firebrigade_node
from backend.agents.rescuenav_bridge import rescuenav_bridge_node


def sense_router(state: dict) -> str:
    """Route to fire or attacker sense based on scenario."""
    return 'attackersense' if state.get('scenario') == 'attacker' else 'firesense'


def route_after_tracksense(state: dict) -> str:
    """Route after tracksense — people are always tracked regardless of threat."""
    level = state.get('threat_level', 'none')
    occupants = state.get('occupant_positions', [])
    rescue_agents = state.get('rescue_agents', [])
    has_at_risk = any(o.get('status') == 'at_risk' for o in occupants)
    has_active_agents = any(a.get('status') != 'standby' for a in rescue_agents)
    has_query = bool(state.get('query'))

    if has_at_risk or has_active_agents:
        return 'dispatch_all'
    if level in ('medium', 'high', 'critical'):
        return 'dispatch_all'
    if level == 'low' or has_query:
        return 'dispatch_comms'
    return 'done'


def build_graph():
    g = StateGraph(EmergencyState)

    g.add_node('orchestrator',      orchestrator_node)
    g.add_node('firesense',         firesense_node)
    g.add_node('attackersense',     attackersense_node)
    g.add_node('tracksense',        tracksense_node)
    g.add_node('routepilot',        routepilot_node)
    g.add_node('systemctrl',        systemctrl_node)
    g.add_node('commrelay',         commrelay_node)
    g.add_node('rescuesim',         rescuesim_node)
    g.add_node('firebrigade',       firebrigade_node)
    g.add_node('rescuenav_bridge',  rescuenav_bridge_node)

    # orchestrator → sense (fire or attacker) → tracksense
    g.set_entry_point('orchestrator')
    g.add_conditional_edges('orchestrator', sense_router, {
        'firesense':    'firesense',
        'attackersense': 'attackersense',
    })
    g.add_edge('firesense',     'tracksense')
    g.add_edge('attackersense', 'tracksense')

    # After tracksense: branch based on threat + occupant status
    g.add_conditional_edges(
        'tracksense', route_after_tracksense,
        {
            'dispatch_all':   'routepilot',
            'dispatch_comms': 'commrelay',
            'done':           'rescuenav_bridge',
        },
    )

    g.add_edge('routepilot',       'systemctrl')
    g.add_edge('systemctrl',       'commrelay')
    g.add_edge('commrelay',        'rescuesim')
    g.add_edge('rescuesim',        'firebrigade')
    g.add_edge('firebrigade',      'rescuenav_bridge')
    g.add_edge('rescuenav_bridge', END)

    return g.compile()


graph = build_graph()


def run_cycle(state: dict) -> dict:
    return graph.invoke(state)
