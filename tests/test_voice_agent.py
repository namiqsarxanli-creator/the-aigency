"""Səsli agent — brauzer nitq tanıması ilə saytda danışan AI operator.

Diqqət nöqtələri:
  * Marşrutlar QƏSDƏN autentifikasiyasızdır (potensial müştəri, hesabı yoxdur) — ona görə
    kvota qorumaq üçün sessiya başına növbə limiti sınanır.
  * `create_brief` əməli yalnız kifayət qədər uzun brif verildikdə layihə yaratmalıdır.
  * LLM sıradan çıxsa/pozuq JSON qaytarsa belə söhbət DAYANMAMALIDIR.
"""
import pytest

from app import voice_agent
from app.db_models import AgentProject, VoiceCall, Workspace
from app.voice_api import MAX_TURNS_PER_SESSION


@pytest.fixture
def workspace(db):
    ws = Workspace(name="The Agency", slug="legacy")
    db.add(ws)
    db.commit()
    return ws


def test_config_returns_greeting_and_session(client):
    response = client.get("/voice/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["greeting"]
    assert len(data["session_id"]) >= 8


def test_config_disabled_returns_404(client, monkeypatch):
    from app.core import settings
    monkeypatch.setattr(settings, "voice_agent_enabled", False)
    assert client.get("/voice/config").status_code == 404


def test_turn_rejects_bad_session_id(client):
    # 8 simvoldan uzun (pydantic min_length keçsin) amma qadağan olunmuş simvol daşıyır
    # (boşluq) — bizim öz `_SESSION_RE` yoxlamamızı tətikləyir, pydantic-i yox.
    response = client.post("/voice/turn", json={"session_id": "a b c d e", "text": "salam"})
    assert response.status_code == 400


def test_turn_returns_llm_reply(client, workspace, monkeypatch):
    monkeypatch.setattr(
        voice_agent, "_call_llm",
        lambda *a, **kw: '{"reply": "Salam, necə kömək edə bilərəm?", "action": "none"}',
    )
    response = client.post(
        "/voice/turn", json={"session_id": "test-session-1", "text": "salam"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "kömək" in data["reply"]
    assert data["action"] == "none"


def test_turn_creates_project_on_create_brief_action(client, db, workspace, monkeypatch):
    monkeypatch.setattr(
        voice_agent, "_call_llm",
        lambda *a, **kw: (
            '{"reply": "Əla, komandamız işə başlayır.", "action": "create_brief", '
            '"brief": "Eko-dostu qəhvə brendi üçün Instagram kampaniyası, gənc auditoriya", '
            '"caller_name": "", "caller_phone": ""}'
        ),
    )
    response = client.post(
        "/voice/turn", json={"session_id": "test-session-2", "text": "eko qəhvə üçün kampaniya istəyirəm"},
    )
    data = response.json()
    assert data["action"] == "create_brief"
    assert data["project_id"] is not None
    project = db.query(AgentProject).filter(AgentProject.id == data["project_id"]).first()
    assert project is not None
    assert project.workspace_id == workspace.id


def test_short_brief_does_not_create_project(db, workspace, monkeypatch):
    """Qısa/mənasız brif layihə yaratmamalıdır — yarımçıq layihə komandanı çaşdırar."""
    monkeypatch.setattr(
        voice_agent, "_call_llm",
        lambda *a, **kw: '{"reply": "Başa düşdüm.", "action": "create_brief", "brief": "bilmirəm"}',
    )
    result = voice_agent.respond(db, workspace.id, "s3", "nəsə")
    assert result["action"] == "none"
    assert db.query(AgentProject).count() == 0


def test_malformed_llm_response_falls_back_gracefully(db, workspace, monkeypatch):
    """LLM boş/pozuq JSON qaytarsa söhbət dayanmamalı, xam mətn cavab kimi işlənməlidir."""
    monkeypatch.setattr(voice_agent, "_call_llm", lambda *a, **kw: "Salam, necəsiniz?")
    result = voice_agent.respond(db, workspace.id, "s4", "salam")
    assert result["reply"]
    assert result["action"] == "none"


def test_llm_failure_returns_fallback_not_crash(db, workspace, monkeypatch):
    monkeypatch.setattr(voice_agent, "_call_llm", lambda *a, **kw: None)
    result = voice_agent.respond(db, workspace.id, "s5", "salam")
    assert result["reply"] == voice_agent.FALLBACK_REPLY


def test_turn_limit_switches_to_handoff(client, db, workspace, monkeypatch):
    monkeypatch.setattr(voice_agent, "_call_llm", lambda *a, **kw: '{"reply": "ok", "action": "none"}')
    call = VoiceCall(session_id="maxed-out", workspace_id=workspace.id, turns=MAX_TURNS_PER_SESSION)
    db.add(call)
    db.commit()

    response = client.post("/voice/turn", json={"session_id": "maxed-out", "text": "davam"})
    data = response.json()
    assert data["action"] == "handoff"


def test_clean_for_speech_strips_markdown_and_emoji():
    dirty = "**Salam!** 😊 - Necə kömək edə *bilərəm*? `test`"
    clean = voice_agent._clean_for_speech(dirty)
    assert "*" not in clean and "`" not in clean and "😊" not in clean
    assert "Salam" in clean and "kömək" in clean


def test_speak_returns_204_without_azure_key(client, monkeypatch):
    from app.core import settings
    monkeypatch.setattr(settings, "azure_speech_key", "")
    response = client.post("/voice/speak", json={"text": "Salam"})
    assert response.status_code == 204


def test_transcript_is_recorded(client, db, workspace, monkeypatch):
    """`append_transcript` marşrut səviyyəsində çağırılır (bax `voice_api.voice_turn`),
    ona görə HTTP marşrutu üzərindən sınayırıq."""
    monkeypatch.setattr(voice_agent, "_call_llm", lambda *a, **kw: '{"reply": "Salam", "action": "none"}')
    client.post("/voice/turn", json={"session_id": "transcript-test", "text": "salam necəsən"})
    call = db.query(VoiceCall).filter(VoiceCall.session_id == "transcript-test").first()
    assert call is not None
    assert "Müştəri" in call.transcript and "AI" in call.transcript
