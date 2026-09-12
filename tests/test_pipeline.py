"""Agent boru xəttinin vəziyyət maşını — BRIEF → IN_PROGRESS → AWAITING_APPROVAL.

Bu testlər real LLM olmadan işləyir (conftest mock-layır), ona görə provayder kvotası
bitəndə də keçirlər — yəni sırf MƏNTİQİ yoxlayırlar, model keyfiyyətini yox.
"""
import pytest

from app.agency import CREATIVE_SEQUENCE, ROLE_SEQUENCE, advance_project, create_project
from app.db_models import AgentTask


def _run_to_completion(db, project, max_steps: int = 40) -> int:
    steps = 0
    while steps < max_steps:
        if advance_project(db, project) is None:
            break
        steps += 1
    return steps


def test_project_starts_in_brief_status(db):
    project = create_project(db, "Test brifi — qəhvə brendi")
    assert project.status == "BRIEF"
    assert project.share_token, "Hər layihənin təxmin edilə bilməyən paylaşım açarı olmalıdır"


def test_planning_creates_all_role_tasks(db):
    project = create_project(db, "Test brifi — landing page")
    advance_project(db, project)

    assert project.status == "IN_PROGRESS"
    roles = [t.role for t in db.query(AgentTask).filter(AgentTask.project_id == project.id).all()]
    assert set(roles) == set(ROLE_SEQUENCE)


def test_planning_is_idempotent(db):
    """Plan iki dəfə qurulsa hər rol üçün TƏKRAR tapşırıq yaranardı və bütün iş ikiqat
    LLM sorğusu ilə təkrarlanardı — bu qoruyucu məhz onun qarşısını alır."""
    project = create_project(db, "Test brifi")
    advance_project(db, project)
    count_after_first = db.query(AgentTask).filter(AgentTask.project_id == project.id).count()

    project.status = "BRIEF"  # planlaşdırmanı süni şəkildə təkrarlayırıq
    db.commit()
    advance_project(db, project)

    count_after_second = db.query(AgentTask).filter(AgentTask.project_id == project.id).count()
    assert count_after_second == count_after_first


def test_full_run_reaches_awaiting_approval(db):
    project = create_project(db, "Tam icra testi — landing page")
    _run_to_completion(db, project)

    assert project.status == "AWAITING_APPROVAL"
    tasks = db.query(AgentTask).filter(AgentTask.project_id == project.id).all()
    assert all(task.status == "DONE" for task in tasks), "Bütün tapşırıqlar DONE olmalıdır"
    assert project.deliverable_html, "Son məhsul yığılmalıdır"


def test_creative_roles_run_before_support_roles(db):
    """Dəstək departamentləri yaradıcı komandanın çıxışını kontekst kimi görməlidir —
    ona görə yaradıcı rollar ƏVVƏL bitməlidir."""
    project = create_project(db, "Sıra testi")
    advance_project(db, project)  # planlaşdırma

    seen_support_before_creative_done = False
    for _ in range(40):
        tasks = {t.role: t.status for t in db.query(AgentTask).filter(AgentTask.project_id == project.id).all()}
        creative_done = all(tasks.get(r) == "DONE" for r in CREATIVE_SEQUENCE)
        support_started = any(
            status != "TODO" for role, status in tasks.items() if role not in CREATIVE_SEQUENCE
        )
        if support_started and not creative_done:
            seen_support_before_creative_done = True
            break
        if advance_project(db, project) is None:
            break

    assert not seen_support_before_creative_done


def test_designer_output_becomes_image_url(db):
    project = create_project(db, "Dizayner testi")
    _run_to_completion(db, project)

    designer = db.query(AgentTask).filter(
        AgentTask.project_id == project.id, AgentTask.role == "designer"
    ).first()
    assert designer.output.startswith("http"), "Dizaynerin çıxışı şəkil URL-i olmalıdır"
    assert project.deliverable_image_url == designer.output


@pytest.mark.parametrize("status", ["AWAITING_APPROVAL", "DELIVERED", "REJECTED"])
def test_terminal_statuses_do_not_advance(db, status):
    project = create_project(db, "Terminal status testi")
    project.status = status
    db.commit()
    assert advance_project(db, project) is None
