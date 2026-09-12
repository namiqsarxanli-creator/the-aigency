"""Workspace izolyasiyası — bir müştəri BAŞQASININ layihəsini görməməlidir.

Bu, layihənin ən kritik təhlükəsizlik zəmanətidir: sistem çox-kirayəçili (multi-tenant) SaaS
kimi işləyir, ona görə hər sorğu yalnız öz workspace-inin məlumatını qaytarmalıdır. Əl ilə
yoxlamaq üçün hər dəfə iki hesab yaratmaq lazım gəlirdi — bu testlər bunu avtomatlaşdırır.
"""


def _create_project(client, brief: str) -> int:
    response = client.post("/agency/brief", json={"brief": brief})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_project_list_only_shows_own_workspace(registered_client):
    alice = registered_client("alice@test.az", "Alice MMC")
    alice_project = _create_project(alice, "Alice-in gizli qəhvə layihəsi")

    bob = registered_client("bob@test.az", "Bob MMC")
    bob_project = _create_project(bob, "Bob-un ayrı layihəsi")

    bob_ids = {item["id"] for item in bob.get("/agency/projects").json()}
    assert bob_project in bob_ids
    assert alice_project not in bob_ids, "Bob Alice-in layihəsini siyahıda görür!"


def test_direct_project_access_is_blocked_across_workspaces(registered_client):
    alice = registered_client("alice2@test.az", "Alice MMC")
    alice_project = _create_project(alice, "Alice-in məxfi brifi")

    bob = registered_client("bob2@test.az", "Bob MMC")
    assert bob.get(f"/agency/{alice_project}").status_code == 404


def test_anonymous_cannot_read_projects(client):
    """Sessiyasız (və API açarsız) sorğu 401 almalıdır."""
    assert client.get("/agency/projects").status_code == 401


def test_regenerate_is_blocked_across_workspaces(registered_client, db):
    """Yeni funksiya da izolyasiyaya tabedir — başqasının tapşırığını yenidən yazdırmaq olmaz."""
    from app.db_models import AgentTask

    alice = registered_client("alice3@test.az", "Alice MMC")
    alice_project = _create_project(alice, "Alice-in layihəsi")
    alice.post(f"/agency/{alice_project}/run")
    task = db.query(AgentTask).filter(AgentTask.project_id == alice_project).first()
    assert task is not None

    bob = registered_client("bob3@test.az", "Bob MMC")
    response = bob.post(f"/agency/{alice_project}/task/{task.id}/regenerate", json={})
    assert response.status_code == 404


def test_export_is_blocked_across_workspaces(registered_client):
    alice = registered_client("alice4@test.az", "Alice MMC")
    alice_project = _create_project(alice, "Alice-in ixrac layihəsi")

    bob = registered_client("bob4@test.az", "Bob MMC")
    assert bob.get(f"/agency/{alice_project}/export/report").status_code == 404
    assert bob.get(f"/agency/{alice_project}/export/zip").status_code == 404


def test_usage_report_is_scoped_to_workspace(registered_client, db):
    """Token hesabatı yalnız öz workspace-inin sorğularını saymalıdır."""
    from app.db_models import LlmUsage, Workspace

    alice = registered_client("alice5@test.az", "Alice MMC")
    alice_ws = db.query(Workspace).filter(Workspace.name == "Alice MMC").first()
    db.add(LlmUsage(
        workspace_id=alice_ws.id, provider="Groq", role="finance",
        prompt_tokens=100, completion_tokens=50, total_tokens=150, ok=True,
    ))
    db.commit()

    assert alice.get("/agency/usage").json()["total_tokens"] == 150

    bob = registered_client("bob5@test.az", "Bob MMC")
    bob_report = bob.get("/agency/usage").json()
    assert bob_report["has_data"] is False
    assert bob_report["total_tokens"] == 0
