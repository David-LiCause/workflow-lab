from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..context import Context
from .nodes import export, make_scrape_node, merge
from .sources import SOURCES
from .state import CollectState

builder = StateGraph(CollectState, context_schema=Context)
for source in SOURCES:  # one scrape node per news site, run in parallel
    builder.add_node(source.node, make_scrape_node(source))
    builder.add_edge(START, source.node)
builder.add_node("merge", merge)
builder.add_node("export", export)
builder.add_edge([s.node for s in SOURCES], "merge")  # waits for every source
builder.add_edge("merge", "export")
builder.add_edge("export", END)

graph = builder.compile()
