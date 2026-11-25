"""The LLM interface everything else is built against, so providers and mocks are swappable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from pydantic import BaseModel

    S = TypeVar("S", bound=BaseModel)


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str = ""


class LLM(Protocol):
    """One interface for any model provider. Swap in a real client or a mock."""

    model: str  # model name; used for logging and cache keys

    def complete(self, messages: list[Message]) -> Message: ...

    def complete_structured(self, messages: list[Message], schema: type[S]) -> S:
        """Answer ``messages`` with an instance of the Pydantic model ``schema``."""
        ...
