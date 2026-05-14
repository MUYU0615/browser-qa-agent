from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    bug_classifier_node,
    component_coverage_executor_node,
    observation_analyzer_node,
    page_analyzer_node,
    reporter_node,
)
from app.graph.state import QAState


def build_workflow():
    graph = StateGraph(QAState)
    graph.add_node("page_analyzer", page_analyzer_node)
    graph.add_node("component_coverage_executor", component_coverage_executor_node)
    graph.add_node("observation_analyzer", observation_analyzer_node)
    graph.add_node("bug_classifier", bug_classifier_node)
    graph.add_node("reporter", reporter_node)

    graph.set_entry_point("page_analyzer")
    graph.add_edge("page_analyzer", "component_coverage_executor")
    graph.add_edge("component_coverage_executor", "observation_analyzer")
    graph.add_edge("observation_analyzer", "bug_classifier")
    graph.add_edge("bug_classifier", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile()
