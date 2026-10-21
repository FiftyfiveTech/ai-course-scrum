.PHONY: setup test gate demo doctor clean
.DEFAULT_GOAL := help

help:
	@echo "make setup   create the venv and install deps (uv)"
	@echo "make test    unit tests"
	@echo "make gate    run every phase gate in tests/gates/"
	@echo "make demo    run the thing end to end"
	@echo "make doctor  PASS/FAIL per external dependency; non-zero exit on any FAIL"

setup:
	@command -v uv >/dev/null || { echo "uv not installed: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	uv sync
	@test -f .env || { cp .env.example .env; echo "wrote .env from .env.example — fill it in"; }
	@echo "ok. next: make test"

test:
	.venv/bin/pytest tests -q --ignore=tests/gates

gate:
	@test -n "$$(ls tests/gates/*.py 2>/dev/null)" || { echo "no gates written yet — see tests/gates/README.md"; exit 1; }
	.venv/bin/pytest tests/gates -q

demo:
	@test -n "$(GROQ_API_KEY)" || { echo "GROQ_API_KEY not set — export it from ~/.config/ before running make demo"; exit 1; }
	PYTHONPATH=. .venv/bin/python -m src.demo

# .venv/bin on Linux/macOS, .venv/Scripts on Windows.
PYTHON := $(firstword $(wildcard .venv/bin/python .venv/Scripts/python.exe))

doctor:
	@test -n "$(PYTHON)" || { echo "no .venv — run make setup first"; exit 1; }
	PYTHONPATH=. $(PYTHON) -m src.doctor

clean:
	rm -rf .venv .pytest_cache **/__pycache__
