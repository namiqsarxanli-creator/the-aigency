from app.core import validate_production_settings


def test_development_settings_do_not_require_production_secrets():
    assert validate_production_settings() == []


def test_health_has_security_headers(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_cross_site_session_mutation_is_blocked(client):
    client.cookies.set("agency_session", "fake-session-is-enough-for-boundary")
    response = client.post("/logout", headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site sorğu bloklandı."
