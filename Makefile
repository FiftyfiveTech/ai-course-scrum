.PHONY: setup test gate demo doctor teams sandbox-up sandbox-down doctor-sandbox clean
.DEFAULT_GOAL := help

# .venv/bin on Linux/macOS, .venv/Scripts on Windows.
PYTHON = $(firstword $(wildcard .venv/bin/python .venv/Scripts/python.exe))
NEED_VENV = @test -n "$(PYTHON)" || { echo "no .venv - run make setup first"; exit 1; }

help:
	@echo "make setup   create the venv and install deps (uv)"
	@echo "make test    unit tests"
	@echo "make gate    run every phase gate in tests/gates/"
	@echo "make demo    run the thing end to end"
	@echo "make doctor  PASS/FAIL per external dependency; non-zero exit on any FAIL"
	@echo "make teams   run the Teams adapter on 127.0.0.1:3978/api/messages (needs a public tunnel for Teams to reach it)"
	@echo "make sandbox-up       local Odoo in Docker on localhost:8069, seeded (sandbox/odoo/)"
	@echo "make doctor-sandbox   make doctor with the Odoo settings pointed at the sandbox"
	@echo "make sandbox-down     stop the sandbox (add WIPE=1 to delete its data)"

setup:
	@command -v uv >/dev/null || { echo "uv not installed: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	uv sync
	@test -f .env || { cp .env.example .env; echo "wrote .env from .env.example — fill it in"; }
	@echo "ok. next: make test"

test:
	$(NEED_VENV)
	$(PYTHON) -m pytest tests -q --ignore=tests/gates

gate:
	@test -n "$$(ls tests/gates/*.py 2>/dev/null)" || { echo "no gates written yet — see tests/gates/README.md"; exit 1; }
	$(NEED_VENV)
	$(PYTHON) -m pytest tests/gates -q

demo:
	@test -n "$(GROQ_API_KEY)" || { echo "GROQ_API_KEY not set — export it from ~/.config/ before running make demo"; exit 1; }
	$(NEED_VENV)
	PYTHONPATH=. $(PYTHON) -m src.demo

doctor:
	$(NEED_VENV)
	PYTHONPATH=. $(PYTHON) -m src.doctor

teams:
	$(NEED_VENV)
	PYTHONPATH=. $(PYTHON) -m src.adapters.teams

SANDBOX = docker compose -f sandbox/odoo/docker-compose.yml

# Local Odoo for testing Odoo code. It is not the course board: a result here is not gate evidence.
sandbox-up:
	$(NEED_VENV)
	$(SANDBOX) up -d db
	$(SANDBOX) run --rm odoo odoo --database sandbox --init project --without-demo all --stop-after-init
	$(SANDBOX) up -d odoo
	$(PYTHON) sandbox/odoo/seed.py

sandbox-down:
	$(SANDBOX) down $(if $(WIPE),--volumes)

# Sandbox Odoo values override for this one command; Groq and Teams still come from your env files.
doctor-sandbox:
	$(NEED_VENV)
	set -a && . sandbox/odoo/sandbox.env && set +a && PYTHONPATH=. $(PYTHON) -m src.doctor

clean:
	rm -rf .venv .pytest_cache **/__pycache__
