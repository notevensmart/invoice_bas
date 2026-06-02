from __future__ import annotations

import os

from app.engine import parser as parser_module
from app.engine.parser import InvoiceParser


def test_parser_disables_llm_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert InvoiceParser().use_llm is False


def test_parser_disables_llm_for_placeholder_api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "replace_with_your_groq_api_key")

    assert InvoiceParser().use_llm is False


def test_parser_enables_llm_for_real_looking_api_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + ("a" * 48))

    assert InvoiceParser().use_llm is True


def test_project_env_loads_without_python_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(parser_module, "load_dotenv", lambda: False)
    (tmp_path / ".env").write_text(
        "GROQ_API_KEY=gsk_" + ("b" * 48) + "\n",
        encoding="utf-8",
    )

    parser_module.load_project_env()

    assert os.environ["GROQ_API_KEY"].startswith("gsk_")
    assert InvoiceParser().use_llm is True
