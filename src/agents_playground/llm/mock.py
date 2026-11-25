"""Scripted LLM for tests and offline development (no API key needed)."""

from __future__ import annotations

from typing import Any, TypeVar

from agents_playground.llm.types import Message

S = TypeVar("S")


class MockLLM:
    """Returns pre-scripted replies in order.

    ``replies`` answer ``complete``. ``structured_replies`` answer ``complete_structured``: each
    is an instance of the requested schema, a dict validated against it, or an exception to raise.
    Every call of either kind is recorded in ``calls``.
    """

    def __init__(
        self,
        replies: list[Message | str] | None = None,
        *,
        structured_replies: list[Any] | None = None,
        model: str = "mock",
    ) -> None:
        self._replies = [
            Message("assistant", r) if isinstance(r, str) else r for r in (replies or [])
        ]
        self._structured_replies = list(structured_replies or [])
        self.model = model
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> Message:
        self.calls.append(list(messages))
        return self._replies.pop(0)

    def complete_structured(self, messages: list[Message], schema: type[S]) -> S:
        self.calls.append(list(messages))
        reply = self._structured_replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, dict):
            return schema.model_validate(reply)  # type: ignore[attr-defined]
        return reply
