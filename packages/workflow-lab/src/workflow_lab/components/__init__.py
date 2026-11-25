"""Reusable components that workflow nodes call.

Available: db (Pydantic rows in SQL), storage (file read/write),
text_to_structured_data (text -> validated Pydantic rows via an LLM),
web_scraper (fetch pages as Markdown/HTML, escalating to a fallback when blocked).
"""
