from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..context import Context
from .nodes import export, extract, fetch_papers
from .state import DigestState


def _after_fetch(state: DigestState) -> str:
    return "extract" if state.get("papers") else END


builder = StateGraph(DigestState, context_schema=Context)
builder.add_node("fetch_papers", fetch_papers)
builder.add_node("extract", extract)
builder.add_node("export", export)
builder.add_edge(START, "fetch_papers")
builder.add_conditional_edges("fetch_papers", _after_fetch, ["extract", END])
builder.add_edge("extract", "export")
builder.add_edge("export", END)

graph = builder.compile()
