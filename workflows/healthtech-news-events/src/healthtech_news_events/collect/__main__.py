"""Run Collect: ``uv run python -m healthtech_news_events.collect``."""

from dotenv import find_dotenv, load_dotenv

from ..context import Context
from .graph import graph

load_dotenv(find_dotenv(usecwd=True))

state = graph.invoke({}, context=Context())
for name, rows in state.get("extracted", {}).items():
    print(f"{name}: {len(rows)} events from {len(state['snapshots'][name])} pages")
print(
    f"Events: {len(state.get('events', []))} ({state.get('inserted', 0)} new, "
    f"{state.get('updated', 0)} updated)"
)
print(f"Review queue: {len(state.get('review_queue', []))}")
for error in state.get("errors", []):
    print(f"Error: {error}")
