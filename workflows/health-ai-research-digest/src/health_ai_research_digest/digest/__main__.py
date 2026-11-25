"""Run the digest: ``uv run python -m health_ai_research_digest.digest``."""

from dotenv import find_dotenv, load_dotenv

from ..context import Context
from .graph import graph

load_dotenv(find_dotenv(usecwd=True))

state = graph.invoke({}, context=Context())
rows = state.get("rows", [])
print(f"Feed: {state.get('feed_path')}")
print(f"Papers: {len(state.get('papers', []))}")
print(
    f"Extracted: {len(rows)} ({sum(r.is_health_ai for r in rows)} health AI); "
    f"{state.get('inserted', 0)} new, {state.get('updated', 0)} updated"
)
print(f"Review queue: {len(state.get('review_queue', []))}")
if state.get("digest_path"):
    print(f"Digest: {state['digest_path']}")
for error in state.get("errors", []):
    print(f"Error: {error}")
