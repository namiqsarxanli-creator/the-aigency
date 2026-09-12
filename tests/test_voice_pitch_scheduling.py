"""Təqdimat zənginin görüş cədvəli — `app.voice_pitch.schedule_meeting`: iş saatları
daxilində bir görüşü təsdiqləyir, dolu vaxta ikinci cəhddə alternativ təklif edir."""
from datetime import timedelta

from app import voice_pitch
from app.voice_pitch import BAKU


def _next_free_business_slot():
    """Testin işlədiyi andan asılı olmayan, gələcəkdə uyğun ilk iş saatını tapır."""
    from datetime import datetime

    start = datetime.now(BAKU) + timedelta(hours=1)
    return next(voice_pitch._iter_business_slots(start))


def _split(slot):
    return slot.strftime("%Y-%m-%d"), slot.strftime("%H:%M")


def test_schedule_confirms_free_slot(db):
    slot = _next_free_business_slot()
    tarix, saat = _split(slot)

    result = voice_pitch.schedule_meeting(db, tarix, saat)

    assert result["ok"] is True
    assert result["status"] == "tesdiqlendi"


def test_schedule_offers_alternative_when_taken(db):
    slot = _next_free_business_slot()
    tarix, saat = _split(slot)

    first = voice_pitch.schedule_meeting(db, tarix, saat)
    assert first["status"] == "tesdiqlendi"

    second = voice_pitch.schedule_meeting(db, tarix, saat)

    assert second["ok"] is True
    assert second["status"] == "dolu"
    assert len(second["alternativler"]) == voice_pitch.MAX_SUGGESTIONS
    assert saat not in second["alternativler"][0]


def test_schedule_rejects_outside_business_hours(db):
    from datetime import datetime

    future_date = (datetime.now(BAKU) + timedelta(days=3)).strftime("%Y-%m-%d")

    result = voice_pitch.schedule_meeting(db, future_date, "22:00")

    assert result["ok"] is True
    assert result["status"] == "dolu"
    assert "kənar" in result["sebeb"]


def test_schedule_rejects_past_datetime(db):
    result = voice_pitch.schedule_meeting(db, "2020-01-01", "11:00")

    assert result["ok"] is False
    assert "keçib" in result["error"]


def test_schedule_rejects_bad_format(db):
    result = voice_pitch.schedule_meeting(db, "sabah", "on bir")

    assert result["ok"] is False
    assert "format" in result["error"].lower()


def test_handle_tool_call_routes_to_schedule_meeting(db_engine, monkeypatch):
    import json

    from sqlalchemy.orm import sessionmaker

    from app import database

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=db_engine))

    slot = _next_free_business_slot()
    tarix, saat = _split(slot)

    result = voice_pitch.handle_tool_call(
        "gorus_teyin_et", json.dumps({"tarix": tarix, "saat": saat}),
    )

    assert result["ok"] is True
    assert result["status"] == "tesdiqlendi"
