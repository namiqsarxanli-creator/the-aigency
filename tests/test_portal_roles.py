from app.db_models import Workspace


def test_customer_sees_portal_navigation_but_not_internal_factory(registered_client, db):
    client = registered_client("client@portal.az", "Müştəri MMC")
    home = client.get("/")
    assert home.status_code == 200
    assert "Brand Kit" in home.text
    assert "Kampaniyalar" in home.text
    assert "Analitika" in home.text
    assert "Satış CRM" not in home.text
    assert "Control Room" not in home.text
    assert ".room-team,.room-operations" in home.text
    assert "/static/brief-assistant.js" in home.text
    assert "/static/voice-agent.js" not in home.text

    for path in ("/sales", "/control-room", "/usage"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"


def test_platform_owner_sees_all_navigation_and_internal_routes(registered_client, db):
    client = registered_client("owner@platform.az", "The Agency")
    workspace = db.query(Workspace).filter(Workspace.name == "The Agency").one()
    workspace.slug = "legacy"
    db.commit()

    home = client.get("/")
    assert "Satış CRM" in home.text
    assert "Control Room" in home.text
    assert ".room-team,.room-operations" not in home.text
    assert client.get("/sales").status_code == 200
    assert client.get("/control-room").status_code == 200
    assert client.get("/usage").status_code == 200
