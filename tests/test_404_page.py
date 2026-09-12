def test_browser_404_uses_branded_page(client):
    response = client.get("/this-page-does-not-exist", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert "The Aigency" in response.text
    assert 'class="nf-main"' in response.text
    assert "/static/404.js" in response.text
    assert "this-page-does-not-exist" in response.text


def test_api_404_remains_json(client):
    response = client.get("/api/does-not-exist", headers={"accept": "application/json"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()
