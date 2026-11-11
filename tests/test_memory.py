from pathlib import Path

import main


def test_timestamped_memory_search_is_session_scoped(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    main.init_db()
    first = main.ensure_session("session_one")
    second = main.ensure_session("session_two")

    stamp = "2026-11-11T03:30:00Z"
    main.save_message(first, "user", "Explain how hybrid retrieval works", stamp)
    main.save_message(second, "user", "Explain how hybrid retrieval works", "2026-11-10T10:00:00Z")

    matches = main.search_memory("hybrid retrieval", first)
    assert len(matches) == 1
    assert matches[0]["created_at"] == stamp
    assert matches[0]["role"] == "user"


def test_recent_messages_are_chronological(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    main.init_db()
    sid = main.ensure_session("session_order")
    main.save_message(sid, "user", "first", "2026-11-11T01:00:00Z")
    main.save_message(sid, "assistant", "second", "2026-11-11T01:00:01Z")

    rows = main.recent_messages(sid)
    assert [row["content"] for row in rows] == ["first", "second"]
