"""LLM interface and clients: ``MockLLM`` always; ``ClaudeLLM`` needs the ``llm`` extra."""

from workflow_lab.llm.mock import MockLLM
from workflow_lab.llm.types import LLM, Message

__all__ = ["LLM", "Message", "MockLLM"]

try:  # ClaudeLLM needs the optional ``llm`` extra
    from workflow_lab.llm.claude import ClaudeError, ClaudeLLM  # noqa: F401
except ImportError:  # pragma: no cover
    pass
else:
    __all__ += ["ClaudeError", "ClaudeLLM"]
