"""
SCRUM-006 — `make doctor` reads env files, not just the shell environment.
"""

from __future__ import annotations

from src import doctor, envfile


def test_parse_handles_comments_export_quotes_and_inline_comments():
    text = """
# a comment
export GROQ_API_KEY=gsk-1
ODOO_WRITE=dry  # off | dry | on
ODOO_LOGIN="scrum bot"
MICROSOFT_APP_PASSWORD='p#ss word'
not a line
=no-key
ODOO_DB=
"""
    assert envfile.parse(text) == {
        "GROQ_API_KEY": "gsk-1",
        "ODOO_WRITE": "dry",
        "ODOO_LOGIN": "scrum bot",
        "MICROSOFT_APP_PASSWORD": "p#ss word",
        "ODOO_DB": "",
    }


def test_environment_beats_local_env_beats_config(tmp_path):
    local, config = tmp_path / "local.env", tmp_path / "config.env"
    local.write_text("ODOO_DB=local\nODOO_LOGIN=local\n", encoding="utf-8")
    config.write_text("ODOO_DB=config\nODOO_LOGIN=config\nODOO_URL=config\n", encoding="utf-8")

    env, read = envfile.load({"ODOO_DB": "shell"}, (local, config))

    assert env["ODOO_DB"] == "shell"
    assert env["ODOO_LOGIN"] == "local"
    assert env["ODOO_URL"] == "config"
    assert read == [local, config]


def test_blank_values_do_not_hide_real_ones(tmp_path):
    # `make setup` copies .env.example to .env: every key present, every value blank.
    local, config = tmp_path / "local.env", tmp_path / "config.env"
    local.write_text("GROQ_API_KEY=\nODOO_WRITE=\n", encoding="utf-8")
    config.write_text("GROQ_API_KEY=gsk-real\nODOO_WRITE=dry\n", encoding="utf-8")

    env, _ = envfile.load({"GROQ_API_KEY": "  "}, (local, config))

    assert env["GROQ_API_KEY"] == "gsk-real"
    assert env["ODOO_WRITE"] == "dry"


def test_missing_files_are_skipped(tmp_path):
    env, read = envfile.load({"A": "1"}, (tmp_path / "nope.env",))
    assert env == {"A": "1"} and read == []


def test_doctor_main_reads_env_files_by_default(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.env"
    config.write_text("ODOO_WRITE=on\n", encoding="utf-8")
    monkeypatch.setattr(envfile, "LOCAL_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(envfile, "CONFIG_ENV", config)
    monkeypatch.delenv("ODOO_WRITE", raising=False)

    def no_network(*args):
        raise ConnectionError("offline")

    doctor.main(http=no_network, common=no_network)
    out = capsys.readouterr().out
    assert f"env files: {config}" in out
    assert "PASS  ODOO_WRITE mode" in out
