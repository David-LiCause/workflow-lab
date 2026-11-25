"""Configurable web scraping with backend escalation. See ``SPEC.md`` for the rules."""

from .backends import BrightDataFetcher, Crawl4AIFetcher, Fetcher
from .config import ScraperConfig, SiteConfig
from .errors import (
    AllBackendsFailed,
    BackendError,
    BackendUnavailable,
    ScraperError,
    ValidationFailed,
)
from .models import Action, FetchRequest, FetchResult
from .scraper import Scraper

__all__ = [
    "Action",
    "AllBackendsFailed",
    "BackendError",
    "BackendUnavailable",
    "BrightDataFetcher",
    "Crawl4AIFetcher",
    "FetchRequest",
    "FetchResult",
    "Fetcher",
    "Scraper",
    "ScraperConfig",
    "ScraperError",
    "SiteConfig",
    "ValidationFailed",
]
