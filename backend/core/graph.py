"""
LangGraph StateGraph assembly — wires all agent nodes.

Routing:
  - ALWAYS: orchestrator → firesense → tracksense (people always visible)
  - threat=none, no query: tracksense → END  (just tracking, no dispatch)
  - threat=low or query:   tracksense → routepilot → commrelay → END
  - threat≥medium or at_risk people: full pipeline including rescue + brigade
"""
from langgraph.graph import StateGraph, END
from backend.core.state import EmergencyState, initial_state
from backend.agents.orchestrator import orchestrator_node
from backend.agents.firesense import firesense_node
from backend.agents.tracksense import tracksense_node
from backend.agents.routepilot import routepilot_node
from backend.agents.systemctrl import systemctrl_node
from backend.agents.commrelay import commrelay_node
from backend.agents.rescuesim import rescuesim_node
from backend.agents.firebrigade import firebrigade_node


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

    g.add_node('orchestrator', orchestrator_node)
    g.add_node('firesense',    firesense_node)
    g.add_node('tracksense',   tracksense_node)
    g.add_node('routepilot',   routepilot_node)
    g.add_node('systemctrl',   systemctrl_node)
    g.add_node('commrelay',    commrelay_node)
    g.add_node('rescuesim',    rescuesim_node)
    g.add_node('firebrigade',  firebrigade_node)

    # Always run: orchestrator → firesense → tracksense
    g.set_entry_point('orchestrator')
    g.add_edge('orchestrator', 'firesense')
    g.add_edge('firesense',    'tracksense')

    # After tracksense: branch based on threat + occupant status
    g.add_conditional_edges(
        'tracksense', route_after_tracksense,
        {
            'dispatch_all':   'routepilot',
            'dispatch_comms': 'commrelay',
            'done':           END,
        },
    )

    g.add_edge('routepilot',  'systemctrl')
    g.add_edge('systemctrl',  'commrelay')
    g.add_edge('commrelay',   'rescuesim')
    g.add_edge('rescuesim',   'firebrigade')
    g.add_edge('firebrigade', END)

    return g.compile()


graph = build_graph()


def run_cycle(state: dict) -> dict:
    return graph.invoke(state)
