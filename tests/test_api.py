import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "_rate_windows", {})
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture()
def mock_llm(monkeypatch):
    """Swap the OpenAI client and web_search for deterministic fakes."""
    completions = types.SimpleNamespace(calls=0)

    def make_completion(content=None, tool_calls=None):
        message = types.SimpleNamespace(content=content, tool_calls=tool_calls)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class FakeCompletions:
        async def create(self, **kwargs):
            completions.calls += 1
            if completions.calls == 1:
                call = types.SimpleNamespace(
                    id="call_1",
                    type="function",
                    function=types.SimpleNamespace(
                        name="web_search",
                        arguments=json.dumps({"query": "current widget news"}),
                    ),
                )
                return make_completion(None, [call])
            return make_completion("Widgets are shipping faster [1].")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

        async def close(self):
            pass

    fake_module = types.ModuleType("openai")
    fake_module.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    async def fake_search_web(query, freshness="any"):
        return [
            {
                "title": "Widget News",
                "url": "https://example.com/widgets",
                "snippet": "Widgets are shipping faster this year.",
                "published": "2026-11-01",
            }
        ]

    monkeypatch.setattr(main, "search_web", fake_search_web)
    monkeypatch.setattr(main, "LLM_API_KEY", "test-key")
    return completions


def test_health_reports_database_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "chronicle-agent", "database": "ok"}


def test_chat_without_llm_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "LLM_API_KEY", "")
    response = client.post("/api/chat", json={"message": "hello", "session_id": "session_nokey"})
    assert response.status_code == 503


def test_history_does_not_create_unknown_session(client):
    response = client.get("/api/history", params={"session_id": "ghost_session"})
    assert response.status_code == 200
    assert response.json() == {"messages": [], "searches": []}
    with sqlite3.connect(main.DB_PATH) as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_history_rejects_invalid_session_id(client):
    response = client.get("/api/history", params={"session_id": "bad id with spaces!"})
    assert response.status_code == 400


def test_chat_tool_loop_persists_sources(client, mock_llm):
    response = client.post(
        "/api/chat",
        json={"message": "What is new in widgets?", "session_id": "session_loop"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Widgets are shipping faster [1]."
    assert body["searches"][0]["result_count"] == 1
    assert body["sources"][0]["number"] == 1
    assert body["sources"][0]["url"] == "https://example.com/widgets"

    history = client.get("/api/history", params={"session_id": "session_loop"}).json()
    roles = [message["role"] for message in history["messages"]]
    assert roles == ["user", "assistant"]
    assistant = history["messages"][1]
    assert assistant["sources"][0]["title"] == "Widget News"
    assert assistant["sources"][0]["number"] == 1
    assert history["searches"][0]["query"] == "current widget news"


def test_memory_search_returns_empty_for_unknown_session(client):
    response = client.get("/api/memory/search", params={"q": "widgets", "session_id": "ghost_session"})
    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_export_unknown_session_returns_404(client):
    response = client.get("/api/export", params={"session_id": "ghost_session"})
    assert response.status_code == 404


def test_export_returns_full_session_json(client, mock_llm):
    client.post("/api/chat", json={"message": "widget news?", "session_id": "session_export"})
    response = client.get("/api/export", params={"session_id": "session_export"})
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")
    payload = response.json()
    assert payload["format"] == "chronicle-export/1"
    assert payload["session"]["id"] == "session_export"
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]
    assert payload["searches"][0]["query"] == "current widget news"


def test_delete_session_removes_all_traces(client, mock_llm):
    client.post("/api/chat", json={"message": "widget news?", "session_id": "session_delete"})
    assert client.get("/api/history", params={"session_id": "session_delete"}).json()["messages"]

    response = client.delete("/api/session", params={"session_id": "session_delete"})
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    history = client.get("/api/history", params={"session_id": "session_delete"}).json()
    assert history == {"messages": [], "searches": []}
    assert client.delete("/api/session", params={"session_id": "session_delete"}).json() == {"deleted": False}

    with sqlite3.connect(main.DB_PATH) as conn:
        for table in ("sessions", "messages", "messages_fts", "tool_events"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_rate_limit_returns_429_after_limit(client, mock_llm, monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 1)
    first = client.post("/api/chat", json={"message": "one", "session_id": "session_rate"})
    assert first.status_code == 200
    second = client.post("/api/chat", json={"message": "two", "session_id": "session_rate"})
    assert second.status_code == 429
    assert "Retry-After" in second.headers
