.PHONY: lint format test

lint:
	ruff check tests/test_topic_validation.py --select F

format:
	ruff format tests/test_topic_validation.py

test:
	pytest tests/test_topic_validation.py
