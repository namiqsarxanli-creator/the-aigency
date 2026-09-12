"""Tək rolu yenidən yazdırma + versiya arxivi.

Ən vacib zəmanət: yeni variant ALINMASA belə köhnə iş İTMƏMƏLİDİR — istifadəçi bir düymə
ilə hazır materialını itirməməlidir.
"""
import pytest

from app import agency
from app.agency import advance_project, create_project, regenerate_task
from app.db_models import AgentTask, AgentTaskVersion


@pytest.fixture
def finished_project(db):
    project = create_project(db, "Yenidən yazma testi — qəhvə brendi")
    for _ in range(40):
        if advance_project(db, project) is None:
            break
    assert project.status == "AWAITING_APPROVAL"
    return project


def _task(db, project, role: str) -> AgentTask:
    return db.query(AgentTask).filter(
        AgentTask.project_id == project.id, AgentTask.role == role
    ).first()


def test_regenerate_archives_previous_output(db, finished_project, monkeypatch):
    task = _task(db, finished_project, "analytics")
    original = task.output

    monkeypatch.setattr(agency, "_call_llm", lambda *a, **kw: "YENİ ANALİTİKA ÇIXIŞI")
    regenerate_task(db, finished_project, task, instruction="KPI-ları daha dəqiq göstər")

    assert task.output == "YENİ ANALİTİKA ÇIXIŞI"
    versions = db.query(AgentTaskVersion).filter(AgentTaskVersion.task_id == task.id).all()
    assert len(versions) == 1
    assert versions[0].version_no == 1
    assert versions[0].output == original, "Köhnə variant olduğu kimi arxivlənməlidir"


def test_regenerate_increments_revision_count(db, finished_project, monkeypatch):
    task = _task(db, finished_project, "marketing")
    monkeypatch.setattr(agency, "_call_llm", lambda *a, **kw: "YENİ MARKETİNQ ÇIXIŞI")

    regenerate_task(db, finished_project, task)
    assert task.revision_count == 1
    regenerate_task(db, finished_project, task)
    assert task.revision_count == 2

    versions = db.query(AgentTaskVersion).filter(AgentTaskVersion.task_id == task.id).all()
    assert sorted(v.version_no for v in versions) == [1, 2]


def test_failed_regenerate_keeps_old_output(db, finished_project, monkeypatch):
    """LLM cavab vermədikdə köhnə iş SAXLANILMALI, saxta versiya sətri YARANMAMALIdır."""
    task = _task(db, finished_project, "marketing")
    original = task.output
    assert original

    monkeypatch.setattr(agency, "_call_llm", lambda *a, **kw: None)
    regenerate_task(db, finished_project, task)

    assert task.output == original, "Uğursuz cəhd hazır işi silməməlidir!"
    assert db.query(AgentTaskVersion).filter(AgentTaskVersion.task_id == task.id).count() == 0


def test_regenerate_does_not_downgrade_delivered_status(db, finished_project, monkeypatch):
    """Təhvil verilmiş layihə yenidən yazdırıldıqda status geri sürüşməməlidir."""
    finished_project.status = "DELIVERED"
    db.commit()

    task = _task(db, finished_project, "developer")  # yaradıcı rol → deliverable yenidən yığılır
    monkeypatch.setattr(agency, "_call_llm", lambda *a, **kw: "<html><body>Yeni</body></html>")
    regenerate_task(db, finished_project, task)

    assert finished_project.status == "DELIVERED"


def test_regenerate_creative_role_refreshes_deliverable(db, finished_project, monkeypatch):
    task = _task(db, finished_project, "developer")
    monkeypatch.setattr(agency, "_call_llm", lambda *a, **kw: "<html><body>TAM YENİ SƏHİFƏ</body></html>")

    regenerate_task(db, finished_project, task)
    assert "TAM YENİ SƏHİFƏ" in finished_project.deliverable_html


def test_regenerate_passes_user_instruction_to_prompt(db, finished_project, monkeypatch):
    """İstifadəçinin göstərişi həqiqətən modelə çatmalıdır."""
    captured = {}

    def _capture(messages, **kwargs):
        captured["user"] = messages[-1]["content"]
        return "cavab"

    monkeypatch.setattr(agency, "_call_llm", _capture)
    regenerate_task(
        db, finished_project, _task(db, finished_project, "analytics"),
        instruction="Yalnız 3 KPI saxla",
    )
    assert "Yalnız 3 KPI saxla" in captured["user"]


def test_regenerate_rejected_while_project_running(registered_client, db):
    """Layihə hələ işləyirsə yenidən yazdırmaq bloklanmalıdır (yarış vəziyyəti riski)."""
    client = registered_client("regen@test.az")
    project_id = client.post("/agency/brief", json={"brief": "İşləyən layihə"}).json()["id"]

    from app.db_models import AgentProject
    project = db.query(AgentProject).filter(AgentProject.id == project_id).first()
    advance_project(db, project)  # planlaşdırma → IN_PROGRESS
    task = db.query(AgentTask).filter(AgentTask.project_id == project_id).first()

    response = client.post(f"/agency/{project_id}/task/{task.id}/regenerate", json={})
    assert response.status_code == 400
