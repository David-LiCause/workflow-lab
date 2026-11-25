"""LLM interface and clients: ``MockLLM`` always; ``ClaudeLLM`` needs the ``llm`` extra."""

from agents_playground.llm.mock import MockLLM
from agents_playground.llm.types import LLM, Message

__all__ = ["LLM", "Message", "MockLLM"]

try:  # ClaudeLLM needs the optional ``llm`` extra
    from agents_playground.llm.claude import ClaudeError, ClaudeLLM  # noqa: F401
except ImportError:  # pragma: no cover
    pass
else:
    __all__ += ["ClaudeError", "ClaudeLLM"]
