"""Run Discovery: ``uv run python -m healthtech_market_landscape_boston.discovery``."""

from dotenv import find_dotenv, load_dotenv

from ..context import Context
from .graph import graph

load_dotenv(find_dotenv(usecwd=True))

state = graph.invoke({}, context=Context())
for name, rows in state.get("extracted", {}).items():
    print(f"{name}: {len(rows)} rows from {state['report_paths'][name]}")
print(
    f"Companies: {len(state.get('companies', []))} ({state.get('inserted', 0)} new, "
    f"{state.get('updated', 0)} updated, {state.get('missing', 0)} missing)"
)
print(f"Review queue: {len(state.get('review_queue', []))}")
for error in state.get("errors", []):
    print(f"Error: {error}")
