"""Fetch backends."""

from .base import Fetcher
from .brightdata import BrightDataFetcher
from .crawl4ai import Crawl4AIFetcher

__all__ = ["BrightDataFetcher", "Crawl4AIFetcher", "Fetcher"]
