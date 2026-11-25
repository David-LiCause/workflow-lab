"""Claude client for the LLM interface, using the Anthropic API's structured output."""

from __future__ import annotations

from typing import Any, TypeVar

from workflow_lab.llm.types import Message

try:
    import anthropic
    from dotenv import find_dotenv, load_dotenv
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ClaudeLLM needs the Anthropic SDK. Install the extra: uv sync --extra llm"
    ) from exc

S = TypeVar("S")

DEFAULT_MODEL = "claude-sonnet-5-5"


class ClaudeError(RuntimeError):
    """Claude declined or could not finish the request."""


class ClaudeLLM:
    """``LLM`` backed by the Anthropic Messages API.

    ``.env`` is loaded first if present. Credentials are then resolved by the Anthropic SDK, in
    order: ``api_key`` (if you pass one), ``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``, the
    active ``ant auth login`` profile. So a key is optional on a machine signed in with ``ant``;
    set ``ANTHROPIC_API_KEY`` for unattended runs (CI, cloud jobs). Retries and timeouts are the
    Anthropic SDK's defaults.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        api_key: str | None = None,
        max_tokens: int = 16000,
        client: Any = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            load_dotenv(find_dotenv(usecwd=True))
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._client = client

    def complete(self, messages: list[Message]) -> Message:
        response = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens, **_split(messages)
        )
        _check_stop(response)
        text = "".join(b.text for b in response.content if b.type == "text")
        return Message("assistant", text)

    def complete_structured(self, messages: list[Message], schema: type[S]) -> S:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            output_format=schema,
            **_split(messages),
        )
        _check_stop(response)
        return response.parsed_output


def _split(messages: list[Message]) -> dict[str, Any]:
    """Anthropic takes system text as a separate argument, not as a message."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    chat = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    kwargs: dict[str, Any] = {"messages": chat}
    if system:
        kwargs["system"] = system
    return kwargs


def _check_stop(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise ClaudeError("Claude declined the request (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise ClaudeError(
            "Claude's reply was cut off at max_tokens; raise max_tokens or chunk less"
        )
