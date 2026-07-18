"""Auth, ownership, and conversation API tests."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DIR = Path(__file__).resolve().parent


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["AUTH_SECRET"] = "test-secret-not-for-prod"
    os.environ["COOKIE_SECURE"] = "0"
    os.environ["CORS_ORIGINS"] = "http://testserver,http://127.0.0.1:5173"

    class _FakeQA:
        def __init__(self, settings):
            self.settings = settings

        def ask(self, question, trace_enabled=True, history=None):
            from backend.app.models import QAResult

            return QAResult(
                question=question,
                answer="## 结论\n测试回答 [S1]",
                sources=[],
                verification={"status": "ok"},
                run_id="test",
                trace_path="test",
                degraded=[],
            )

        def ask_stream(self, question, trace_enabled=True, history=None):
            yield {"type": "meta", "route": "evidence", "generation_mode": "text", "sources": [], "run_id": "test"}
            yield {"type": "token", "text": "## 结论\n"}
            yield {"type": "token", "text": "测试流式"}
            payload = {
                "question": question,
                "answer_markdown": "## 结论\n测试流式",
                "answer_paragraphs": ["## 结论\n测试流式"],
                "sources": [],
                "figures": [],
                "attached_references": [],
                "reference_links": {},
                "graph_triples": [],
                "verification": {"status": "ok"},
                "degraded": [],
                "run_id": "test",
                "trace_path": "test",
                "generation_mode": "text",
                "answer_kind": "guideline",
                "trace": {},
            }
            yield {"type": "final", "payload": payload}

    # Reset DB / web config caches so env is re-read.
    import backend.app.db as dbmod
    from backend.app.web_config import reset_web_config_cache

    reset_web_config_cache()
    if dbmod._engine is not None:
        dbmod._engine.dispose()
    dbmod._engine = None
    dbmod._SessionLocal = None

    monkeypatch.setattr("backend.api.server.QAService", _FakeQA)

    from backend.app.db import init_db
    from backend.api.server import create_app

    init_db()
    app = create_app()
    with TestClient(app) as c:
        yield c

    if dbmod._engine is not None:
        dbmod._engine.dispose()
    dbmod._engine = None
    dbmod._SessionLocal = None


def test_register_login_me_logout(client: TestClient):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"
    assert client.cookies.get("guideflow_session")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"

    client.post("/api/auth/logout")
    me2 = client.get("/api/auth/me")
    assert me2.status_code == 200
    assert me2.json() is None

    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrongpass1"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert ok.status_code == 200


def test_conversation_idor(client: TestClient):
    client.post("/api/auth/register", json={"email": "owner@example.com", "password": "password123"})
    created = client.post("/api/conversations", json={"title": "私有会话"})
    assert created.status_code == 200
    conv_id = created.json()["id"]

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "other@example.com", "password": "password123"})

    stolen = client.get(f"/api/conversations/{conv_id}")
    assert stolen.status_code == 404

    deleted = client.delete(f"/api/conversations/{conv_id}")
    assert deleted.status_code == 404


def test_ask_stream_and_persist(client: TestClient):
    client.post("/api/auth/register", json={"email": "stream@example.com", "password": "password123"})
    with client.stream(
        "POST",
        "/api/ask",
        json={"question": "流式测试问题", "stream": True, "trace": False},
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes()).decode("utf-8")
    assert "测试流式" in body
    assert '"type": "final"' in body or '"type":"final"' in body

    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert len(listing.json()) >= 1
    detail = client.get(f"/api/conversations/{listing.json()[0]['id']}")
    assert detail.status_code == 200
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant"]


def test_share_public(client: TestClient):
    client.post("/api/auth/register", json={"email": "share@example.com", "password": "password123"})
    conv = client.post("/api/conversations", json={"title": "可分享"}).json()
    client.post("/api/ask", json={"question": "分享测试", "stream": False, "conversation_id": conv["id"]})
    listing = client.get("/api/conversations").json()
    conv_id = listing[0]["id"]
    shared = client.post(f"/api/conversations/{conv_id}/share")
    assert shared.status_code == 200
    token = shared.json()["token"]

    client.post("/api/auth/logout")
    pub = client.get(f"/api/shared/{token}")
    assert pub.status_code == 200
    assert pub.json()["id"] == conv_id


def _ask(client: TestClient, question: str, **extra) -> dict:
    resp = client.post(
        "/api/ask",
        json={"question": question, "stream": False, "trace": False, **extra},
    )
    assert resp.status_code == 200
    return resp.json()


def test_message_tree_followup_and_regen(client: TestClient):
    client.post("/api/auth/register", json={"email": "tree@example.com", "password": "password123"})
    first = _ask(client, "第一问")
    conv_id = first["conversation_id"]
    user1 = first["user_message_id"]
    asst1 = first["assistant_message_id"]
    assert user1 and asst1

    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert detail["active_root_id"] == user1
    assert len(detail["messages"]) == 2
    by_id = {m["id"]: m for m in detail["messages"]}
    assert by_id[user1]["parent_id"] is None
    assert by_id[asst1]["parent_id"] == user1
    assert by_id[user1]["active_child_id"] == asst1

    # Follow-up under assistant leaf
    second = _ask(client, "第二问", conversation_id=conv_id, parent_message_id=asst1)
    user2 = second["user_message_id"]
    asst2 = second["assistant_message_id"]

    # Regenerate under first user → sibling assistant
    regen = _ask(
        client,
        "第一问",
        conversation_id=conv_id,
        parent_message_id=user1,
        regenerate=True,
    )
    asst1b = regen["assistant_message_id"]
    assert regen["user_message_id"] == user1
    assert asst1b != asst1

    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert len(detail["messages"]) == 5  # u1,a1,u2,a2,a1b
    by_id = {m["id"]: m for m in detail["messages"]}
    assert by_id[user1]["active_child_id"] == asst1b
    kids = [m["id"] for m in detail["messages"] if m["parent_id"] == user1]
    assert set(kids) == {asst1, asst1b}

    # Switch active branch back to asst1
    sw = client.post(
        f"/api/conversations/{conv_id}/active-branch",
        json={"message_id": asst1},
    )
    assert sw.status_code == 200
    detail = client.get(f"/api/conversations/{conv_id}").json()
    by_id = {m["id"]: m for m in detail["messages"]}
    assert by_id[user1]["active_child_id"] == asst1

    # Shared view is linearized active path (u1 -> asst1 -> u2 -> asst2)
    token = client.post(f"/api/conversations/{conv_id}/share").json()["token"]
    shared = client.get(f"/api/shared/{token}").json()
    shared_ids = [m["id"] for m in shared["messages"]]
    assert shared_ids == [user1, asst1, user2, asst2]


def test_delete_message_branch(client: TestClient):
    client.post("/api/auth/register", json={"email": "del@example.com", "password": "password123"})
    first = _ask(client, "根问题")
    conv_id = first["conversation_id"]
    user1 = first["user_message_id"]
    asst1 = first["assistant_message_id"]

    # Edit-style sibling root question
    second = _ask(client, "根问题改写", conversation_id=conv_id, parent_message_id=None)
    user2 = second["user_message_id"]
    asst2 = second["assistant_message_id"]
    # Second ask with null parent creates another root; point active root to user2 happens automatically
    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert detail["active_root_id"] == user2

    # Follow-up on second branch
    _ask(client, "分支追问", conversation_id=conv_id, parent_message_id=asst2)

    # Delete second root branch — should keep first branch and retarget active_root
    deleted = client.delete(f"/api/messages/{user2}")
    assert deleted.status_code == 200
    body = deleted.json()
    assert user2 in body["deleted"]
    assert asst2 in body["deleted"]
    assert body["fallback_id"] == user1

    detail = client.get(f"/api/conversations/{conv_id}").json()
    ids = {m["id"] for m in detail["messages"]}
    assert user1 in ids and asst1 in ids
    assert user2 not in ids and asst2 not in ids
    assert detail["active_root_id"] == user1
