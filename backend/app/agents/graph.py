"""The LangGraph StateGraph.

Topology::

    START
      └─> data_ingestion ──(failed)──> END
                 │
                 └─> fundamental ─> sentiment_analyst ─> technical_analyst
                                                        │
                                                        v
                                                      bull <──┐
                                                        │     │ round < max
                                                        v     │
                                                       bear ──┘
                                                        │ round == max
                                                        v
                                                  risk_manager ─> decision ─> translation ─> END

Node names deliberately differ from GraphState keys — LangGraph rejects a node
whose name collides with a state channel ("sentiment is already being used as
a state key").

Only the quantitative layer is deterministic; the analysts and the debate
contribute at most +/-15 points to the final score, which keeps a prompt
change from silently rewriting a backtest result.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.bear import bear_node
from app.agents.nodes.bull import bull_node
from app.agents.nodes.data_ingestion import data_ingestion_node
from app.agents.nodes.decision import decision_node
from app.agents.nodes.fundamental import fundamental_node
from app.agents.nodes.risk import risk_node
from app.agents.nodes.sentiment import sentiment_node
from app.agents.nodes.technical import technical_node
from app.agents.nodes.translation import translation_node
from app.agents.state import GraphState

_NODE_NAMES = (
    "data_ingestion",
    "fundamental",
    "sentiment_analyst",
    "technical_analyst",
    "bull",
    "bear",
    "risk_manager",
    "decision",
    "translation",
)


def _route_after_data(state: GraphState) -> str:
    return END if state.get("failed") else "fundamental"


def _route_after_bear(state: GraphState) -> str:
    """Keep debating while rounds remain, then hand over to the risk manager."""
    current = int(state.get("debate_round", 0))
    maximum = int(state.get("debate_max_rounds", 1))
    return "bull" if current < maximum else "risk_manager"


def build_graph():
    """Compile the graph. Call once and reuse — the graph is stateless."""
    graph = StateGraph(GraphState)

    graph.add_node("data_ingestion", data_ingestion_node)
    graph.add_node("fundamental", fundamental_node)
    graph.add_node("sentiment_analyst", sentiment_node)
    graph.add_node("technical_analyst", technical_node)
    graph.add_node("bull", bull_node)
    graph.add_node("bear", bear_node)
    graph.add_node("risk_manager", risk_node)
    graph.add_node("decision", decision_node)
    graph.add_node("translation", translation_node)

    graph.add_edge(START, "data_ingestion")
    graph.add_conditional_edges(
        "data_ingestion",
        _route_after_data,
        {"fundamental": "fundamental", END: END},
    )
    graph.add_edge("fundamental", "sentiment_analyst")
    graph.add_edge("sentiment_analyst", "technical_analyst")
    graph.add_edge("technical_analyst", "bull")
    graph.add_edge("bull", "bear")
    graph.add_conditional_edges(
        "bear",
        _route_after_bear,
        {"bull": "bull", "risk_manager": "risk_manager"},
    )
    graph.add_edge("risk_manager", "decision")
    graph.add_edge("decision", "translation")
    graph.add_edge("translation", END)

    return graph.compile()
