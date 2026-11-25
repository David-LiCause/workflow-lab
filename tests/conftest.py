"""Shared test fixtures.

Unit tests run by default. Integration tests (marked ``integration``, in each component's
``integration/`` folder) only run with ``uv run pytest -m integration``. They fail, rather than
skip, when a required env var is missing, so an unrun test is easy to see.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@pytest.fixture
def require_env() -> Callable[..., dict[str, str]]:
    """Return ``require(*names)``: the env vars' values, or fail the test if any are missing.

    Loads the project ``.env`` first (existing env vars win).
    """
    load_dotenv(ENV_FILE, override=False)

    def require(*names: str) -> dict[str, str]:
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            pytest.fail(
                f"Missing env var(s): {', '.join(missing)}. Set them in .env (see .env.example).",
                pytrace=False,
            )
        return {n: os.environ[n] for n in names}

    return require


NO_ANTHROPIC_CREDENTIALS = (
    "No Anthropic credentials: run `ant auth login` or set ANTHROPIC_API_KEY in .env."
)


def ant_has_active_credential() -> bool:
    """True if ``ant auth status`` shows an ``(active)`` row in its Credentials block.

    ``ant`` missing, failing or timing out counts as not signed in.
    """
    try:
        out = subprocess.run(
            ["ant", "auth", "status"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    in_block = False
    for line in out.splitlines():
        if line.strip() == "Credentials":
            in_block = True
        elif in_block and not line.strip():
            break  # a blank line ends the block
        elif in_block and "(active)" in line:
            return True
    return False


@pytest.fixture
def require_anthropic_credentials() -> None:
    """Pass if Claude credentials are available; otherwise FAIL (never skip).

    Credentials are ``ANTHROPIC_API_KEY`` or ``ANTHROPIC_AUTH_TOKEN`` (after loading the project
    ``.env``), or an active ``ant auth login`` profile. Empty values count as unset.
    """
    load_dotenv(ENV_FILE, override=False)
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return
    if ant_has_active_credential():
        return
    pytest.fail(NO_ANTHROPIC_CREDENTIALS, pytrace=False)
