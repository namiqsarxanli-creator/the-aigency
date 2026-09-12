"""Test qurulumu — izolyasiya edilmiş verilənlər bazası və şəbəkəsiz (mock) LLM.

NİYƏ DEPENDENCY OVERRIDE: `.env`-dəki `DATABASE_URL` `load_dotenv(override=True)` ilə oxunur,
yəni `os.environ`-u ƏVƏZ EDİR — ona görə testdən əvvəl mühit dəyişəni qoymaqla real bazadan
ayrılmaq mümkün deyil. FastAPI-nin `dependency_overrides` mexanizmi bu problemi tamamilə həll
edir: tətbiq eyni qalır, yalnız `get_db` test bazasına yönləndirilir.

HEÇ BİR TEST ŞƏBƏKƏYƏ ÇIXMIR: `_call_llm` və `find_stock_photo` avtomatik mock-lanır
(`autouse` fixture) — testlər LLM kvotası yandırmır və provayder işləmədikdə də keçir.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from app import agency, campaign_ai, openai_images, stock_photos, studio_ai  # noqa: E402
from app.database import Base, get_db  # noqa: E402


@pytest.fixture(scope="function")
def db_engine():
    """Hər test üçün təmiz, yaddaşdaxili baza.

    `StaticPool` + `check_same_thread=False`: `advance_project` `asyncio.to_thread` ilə başqa
    thread-dən çağırılır, ona görə eyni bağlantı bütün thread-lərdə paylaşılmalıdır — əks halda
    yaddaşdaxili baza hər thread üçün BOŞ görünər.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db(db_engine):
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine, db):
    """Autentifikasiyasız test client.

    QƏSDƏN `with` BLOKU İSTİFADƏ EDİLMİR: `TestClient` yalnız kontekst meneceri kimi
    işlədiləndə startup event-lərini işə salır — biz isə arxa fon `agency_loop`
    planlayıcısının testlər zamanı layihələri öz-özünə irəlilətməsini İSTƏMİRİK.
    """
    main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def registered_client(db_engine, db):
    """Qeydiyyatdan keçmiş, sessiya cookie-si olan client (workspace sahibi)."""
    main.app.dependency_overrides[get_db] = lambda: db
    test_client = TestClient(main.app)

    def _register(email: str, company: str = "Test Şirkət"):
        response = test_client.post(
            "/register",
            data={
                "full_name": "Test İstifadəçi", "company_name": company,
                "email": email, "password": "TestPass1234",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        return test_client

    try:
        yield _register
    finally:
        main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Şəbəkə mock-ları — heç bir test real API çağırmır.
# ---------------------------------------------------------------------------

FAKE_PLAN = {
    "output_type": "landing_page",
    "tasks": [
        {"role": role, "title": f"{role} işi", "description": f"{role} tapşırığı"}
        for role in agency.ROLE_SEQUENCE
    ],
}


def fake_llm_response(messages, **kwargs):
    """System prompt-a görə uyğun saxta cavab qaytarır (JSON gözləyənlərə JSON)."""
    system = (messages[0].get("content") or "") if messages else ""
    if "orkestrator" in system.lower():
        return json.dumps(FAKE_PLAN)
    if "Tənqidçi" in system or "QA-san" in system:
        return json.dumps({"verdict": "APPROVE", "feedback": "test təsdiqi"})
    return "TEST ÇIXIŞI — bu, mock LLM cavabıdır."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Bütün testlərdə LLM və şəkil axtarışını söndürür."""
    monkeypatch.setattr(agency, "_call_llm", lambda messages, **kw: fake_llm_response(messages, **kw))
    # `studio_ai` `_call_llm`-i DƏYƏRLƏ import edir (`from app.agency import _call_llm`),
    # ona görə yuxarıdakı patch ona təsir etmir — ayrıca söndürülməlidir, əks halda
    # testlər həqiqi provayderə çıxır (canlı sınaqda 429 ilə üzə çıxdı).
    monkeypatch.setattr(studio_ai, "_call_llm", lambda messages, **kw: None)
    monkeypatch.setattr(campaign_ai, "_call_llm", lambda messages, **kw: None)
    # OpenAI şəkil generasiyası da söndürülür — testlər ödənişli açara çıxmasın.
    monkeypatch.setattr(openai_images, "generate", lambda *a, **kw: None)
    # Şəkil axtarışı da mənbə modulda söndürülür — `content_studio` onu modul üzərindən
    # çağırır, ona görə tək bir patch bütün istifadəçiləri əhatə edir.
    monkeypatch.setattr(
        stock_photos, "find_stock_photo",
        lambda *a, **kw: type("Photo", (), {
            "url": "https://example.test/photo.jpg", "source": "TestStock",
            "credit": "Test Müəllif", "page_url": "https://example.test/p/1",
        })(),
    )
    monkeypatch.setattr(
        agency, "find_stock_photo",
        lambda *a, **kw: type("Photo", (), {
            "url": "https://example.test/photo.jpg", "source": "TestStock",
            "credit": "Test Müəllif", "page_url": "https://example.test/p/1",
        })(),
    )
    # Bufer testlər arasında sızmasın (modul səviyyəli qlobal siyahıdır).
    with agency._USAGE_LOCK:
        agency._USAGE_BUFFER.clear()
    agency._PROVIDER_COOLDOWN.clear()
    yield
    with agency._USAGE_LOCK:
        agency._USAGE_BUFFER.clear()
