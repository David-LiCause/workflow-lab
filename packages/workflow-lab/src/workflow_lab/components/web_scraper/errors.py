"""Exceptions raised by the scraper."""


class ScraperError(Exception):
    """Base class for all scraper errors."""


class BackendError(ScraperError):
    """A backend failed to fetch a page (network error, blocked, timeout, ...)."""


class BackendUnavailable(BackendError):
    """A backend can't be used (e.g. missing credentials). Recorded, then the next one is tried."""


class ValidationFailed(ScraperError):
    """A fetched page did not pass validation (challenge page, too short, ...)."""


class AllBackendsFailed(ScraperError):
    """Every backend in the chain failed for a request."""
