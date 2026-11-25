"""Scraper configuration. Loading from YAML is a TODO; for now build these in code."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .models import Action


@dataclass
class SiteConfig:
    """Per-site overrides, matched by domain."""

    backend: str | None = None  # force a specific backend for this site
    actions: tuple[Action, ...] = ()
    required_selector: str | None = None
    min_chars: int | None = None
    rate_limit_s: float | None = None


@dataclass
class ScraperConfig:
    """Top-level scraper settings."""

    backend: str = "crawl4ai"  # primary backend name
    fallbacks: list[str] = field(default_factory=lambda: ["brightdata"])
    min_chars: int = 1500
    rate_limit_s: float = 3.0  # minimum delay between requests to one domain
    user_agent: str = "web-scraper (set a contact here)"
    sites: dict[str, SiteConfig] = field(default_factory=dict)  # domain -> overrides

    @classmethod
    def from_yaml(cls, path: str | Path) -> ScraperConfig:
        """Load config from a YAML file. TODO: implement (needs a YAML dependency)."""
        raise NotImplementedError("YAML config loading is not implemented yet")
