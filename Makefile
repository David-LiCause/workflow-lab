.PHONY: studio notebook

studio: ## Start LangGraph Studio for the graphs in langgraph.json (http://127.0.0.1:2024)
	uv run langgraph dev

notebook: ## Open the marimo notebook for querying every workflow's data (notebooks/explore.py)
	uv run marimo edit notebooks/explore.py
