from __future__ import annotations

import logging

from tracker_assistant.shared.logging import configure_logging


def _reset_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.NOTSET)


def test_cli_level_overrides_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    _reset_logging()
    configure_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_env_level_used_when_no_cli(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    _reset_logging()
    configure_logging(None)
    assert logging.getLogger().level == logging.DEBUG


def test_default_warning_when_nothing_set(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    _reset_logging()
    configure_logging(None)
    assert logging.getLogger().level == logging.WARNING


def test_invalid_level_falls_back_to_warning(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "BADLEVEL")
    _reset_logging()
    configure_logging(None)
    assert logging.getLogger().level == logging.WARNING
