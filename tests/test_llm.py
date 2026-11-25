import os
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agents_playground.llm import ClaudeError, ClaudeLLM, Message, MockLLM
from agents_playground.llm import claude as claude_module


def test_mock_llm_returns_scripted_replies_in_order():
    llm = MockLLM(["first", Message("assistant", "second")])
    assert llm.complete([Message("user", "a")]).content == "first"
    assert llm.complete([Message("user", "b")]).content == "second"
    assert len(llm.calls) == 2


class _Item(BaseModel):
    name: str


def test_mock_llm_structured_replies_accept_instances_dicts_and_errors():
    llm = MockLLM(structured_replies=[_Item(name="a"), {"name": "b"}, RuntimeError("boom")])
    assert llm.complete_structured([Message("user", "x")], _Item).name == "a"
    assert llm.complete_structured([Message("user", "x")], _Item) == _Item(name="b")
    with pytest.raises(RuntimeError):
        llm.complete_structured([Message("user", "x")], _Item)
    assert len(llm.calls) == 3
    assert llm.model == "mock"


class _FakeMessages:
    def __init__(self, stop_reason: str = "end_turn") -> None:
        self.stop_reason = stop_reason
        self.kwargs: dict = {}

    def _response(self):
        text = SimpleNamespace(type="text", text="hi")
        return SimpleNamespace(
            stop_reason=self.stop_reason, content=[text], parsed_output=_Item(name="parsed")
        )

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self._response()

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self._response()


def _claude(stop_reason: str = "end_turn"):
    messages = _FakeMessages(stop_reason)
    llm = ClaudeLLM("some-model", client=SimpleNamespace(messages=messages))
    return llm, messages


def test_claude_complete_sends_system_separately():
    llm, fake = _claude()
    reply = llm.complete([Message("system", "be brief"), Message("user", "hello")])
    assert reply == Message("assistant", "hi")
    assert fake.kwargs["model"] == "some-model"
    assert fake.kwargs["system"] == "be brief"
    assert fake.kwargs["messages"] == [{"role": "user", "content": "hello"}]


def test_claude_complete_structured_passes_schema_and_returns_parsed():
    llm, fake = _claude()
    result = llm.complete_structured([Message("user", "hello")], _Item)
    assert result == _Item(name="parsed")
    assert fake.kwargs["output_format"] is _Item
    assert "system" not in fake.kwargs


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_raises_when_reply_is_unusable(stop_reason):
    llm, _ = _claude(stop_reason)
    with pytest.raises(ClaudeError):
        llm.complete_structured([Message("user", "hello")], _Item)


class _FakeAnthropic:
    """Stands in for ``anthropic.Anthropic``: records how it was built; no network."""

    instances: list["_FakeAnthropic"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.env_key = os.environ.get("ANTHROPIC_API_KEY")
        self.messages = None
        _FakeAnthropic.instances.append(self)


@pytest.fixture
def fake_sdk(monkeypatch, tmp_path):
    """No network, no real credentials, and an empty working dir (so no stray .env)."""
    _FakeAnthropic.instances = []
    monkeypatch.setattr(claude_module.anthropic, "Anthropic", _FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    monkeypatch.delenv("ANTHROPIC_API_KEY")  # restored (to unset) when the test ends
    monkeypatch.chdir(tmp_path)
    return _FakeAnthropic


def test_claude_passes_an_explicit_api_key_to_the_sdk(fake_sdk):
    ClaudeLLM(api_key="sk-explicit")
    assert fake_sdk.instances[0].kwargs == {"api_key": "sk-explicit"}


def test_claude_picks_up_a_key_from_dotenv(fake_sdk, tmp_path):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-from-dotenv\n")
    ClaudeLLM()
    sdk = fake_sdk.instances[0]
    assert sdk.kwargs == {}  # the SDK reads the env var itself
    assert sdk.env_key == "sk-from-dotenv"


def test_claude_without_a_key_builds_the_client_without_api_key(fake_sdk):
    ClaudeLLM()
    assert fake_sdk.instances[0].kwargs == {}  # SDK falls back to `ant auth login`
