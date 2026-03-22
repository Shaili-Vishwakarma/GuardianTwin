"""
LangGraph StateGraph assembly — wires all 6 agent nodes.
"""
from langgraph.graph import StateGraph, END
from backend.core.state import EmergencyState, initial_state
from backend.agents.orchestrator import orchestrator_node
from backend.agents.firesense import firesense_node
from backend.agents.tracksense import tracksense_node
from backend.agents.routepilot import routepilot_node
from backend.agents.systemctrl import systemctrl_node
from backend.agents.commrelay import commrelay_node


def route_after_orchestrator(state: dict) -> str:
    level = state.get('threat_level', 'none')
    if level in ('medium', 'high', 'critical'):
        return 'dispatch_all'
    if level == 'low':
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

    g.set_entry_point('orchestrator')
    g.add_conditional_edges(
        'orchestrator',
        route_after_orchestrator,
        {
            'dispatch_all':   'firesense',
            'dispatch_comms': 'commrelay',
            'done':           END,
        },
    )
    g.add_edge('firesense',  'tracksense')
    g.add_edge('tracksense', 'routepilot')
    g.add_edge('routepilot', 'systemctrl')
    g.add_edge('systemctrl', 'commrelay')
    g.add_edge('commrelay',  END)

    return g.compile()


graph = build_graph()


def run_cycle(state: dict) -> dict:
    return graph.invoke(state)
