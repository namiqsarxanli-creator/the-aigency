"""Token qeydiyyatı — sorğular buferə yığılır, sonra ƏSAS thread-də bazaya yazılır.

Kritik dizayn qaydası: `_call_provider` paralel worker thread-lərdən çağırılır, ona görə
DB-yə BİRBAŞA yazmamalıdır. Bu testlər həmin sərhədi qoruyur.
"""
import requests

from app import agency
from app.agency import flush_usage
from app.db_models import LlmUsage
from app.usage_report import build_usage_report


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


PROVIDER = {"name": "TestProvider", "url": "https://example.test/v1", "key": "k", "model": "test-model"}
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_successful_call_records_token_usage(db, monkeypatch):
    payload = {
        "choices": [{"message": {"content": "cavab"}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
    }
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse(200, payload))

    result = agency._call_provider(
        PROVIDER, MESSAGES, 100, 0.5, usage_ctx={"workspace_id": 1, "project_id": 2, "role": "finance"},
    )
    assert result == "cavab"

    assert flush_usage(db) == 1
    row = db.query(LlmUsage).one()
    assert (row.provider, row.role, row.total_tokens, row.ok) == ("TestProvider", "finance", 165, True)
    assert row.prompt_tokens == 120 and row.completion_tokens == 45


def test_rate_limited_call_is_recorded_as_failure(db, monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse(429, text="Please try again in 3.5s"),
    )

    assert agency._call_provider(PROVIDER, MESSAGES, 100, 0.5, usage_ctx={"workspace_id": 1}) is None

    flush_usage(db)
    row = db.query(LlmUsage).one()
    assert row.ok is False
    assert row.error_kind == "rate_limit"


def test_payment_error_is_recorded_and_provider_cooled_down(db, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse(402, text="Payment required"))

    assert agency._call_provider(PROVIDER, MESSAGES, 100, 0.5, usage_ctx={"workspace_id": 1}) is None

    flush_usage(db)
    assert db.query(LlmUsage).one().error_kind == "payment"
    assert "TestProvider" in agency._PROVIDER_COOLDOWN, "402 sonrası provayder söndürülməlidir"


def test_call_provider_does_not_touch_database(monkeypatch):
    """Bu, əvvəl tapılmış KRİTİK bugun qoruyucusudur: paralel thread-lərdən DB-yə toxunmaq
    SQLite korrupsiyasına səbəb olurdu. `_call_provider` yalnız buferə yazmalıdır."""
    payload = {"choices": [{"message": {"content": "x"}}], "usage": {"total_tokens": 10}}
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse(200, payload))

    agency._call_provider(PROVIDER, MESSAGES, 100, 0.5, usage_ctx={"workspace_id": 1})

    with agency._USAGE_LOCK:
        assert len(agency._USAGE_BUFFER) == 1, "Qeyd buferdə olmalıdır (DB-də yox)"


def test_flush_is_idempotent(db, monkeypatch):
    payload = {"choices": [{"message": {"content": "x"}}], "usage": {"total_tokens": 10}}
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse(200, payload))
    agency._call_provider(PROVIDER, MESSAGES, 100, 0.5, usage_ctx={"workspace_id": 1})

    assert flush_usage(db) == 1
    assert flush_usage(db) == 0, "Təkrar flush eyni sətri iki dəfə yazmamalıdır"
    assert db.query(LlmUsage).count() == 1


def test_report_groups_by_provider_and_role(db):
    db.add_all([
        LlmUsage(workspace_id=1, provider="Groq", role="finance", total_tokens=300, ok=True),
        LlmUsage(workspace_id=1, provider="Groq", role="legal", total_tokens=200, ok=True),
        LlmUsage(workspace_id=1, provider="Gemini", role="finance", total_tokens=100, ok=False,
                 error_kind="rate_limit"),
    ])
    db.commit()

    report = build_usage_report(db, workspace_id=1)
    assert report["has_data"] is True
    assert report["total_calls"] == 3
    assert report["total_tokens"] == 600
    assert report["failed_calls"] == 1

    providers = {row["label"]: row for row in report["by_provider"]}
    assert providers["Groq"]["total_tokens"] == 500
    assert providers["Groq"]["ok_calls"] == 2
    assert providers["Gemini"]["ok_calls"] == 0

    # Ən çox token sərf edən rol birinci olmalıdır (panel bunu belə göstərir).
    assert report["by_role"][0]["label"] == "Maliyyə"
    assert report["failures"] == {"Limit doldu (429)": 1}


def test_empty_report_when_no_usage(db):
    report = build_usage_report(db, workspace_id=999)
    assert report["has_data"] is False
    assert report["by_provider"] == [] and report["by_role"] == []
