from app import lead_finder


class Response:
    ok = True
    text = "ok"

    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


def test_global_city_and_country_are_sent_to_geocoder(monkeypatch):
    captured = {}

    def fake_get(url, params, **kwargs):
        captured.update(params)
        return Response([{
            "boundingbox": ["41.0", "41.2", "28.8", "29.2"],
            "address": {"city": "İstanbul", "country": "Türkiye"},
        }])

    monkeypatch.setattr(lead_finder.requests, "get", fake_get)
    monkeypatch.setattr(lead_finder.requests, "post", lambda *a, **k: Response({"elements": [{
        "type": "node", "id": 10,
        "tags": {"name": "Global Cafe", "amenity": "cafe", "contact:phone": "+90"},
    }]}))

    results = lead_finder.discover_businesses("İstanbul", "restaurant", country="Türkiyə")

    assert captured["q"] == "İstanbul, Türkiyə"
    assert captured["featuretype"] == "city"
    assert results[0].city == "İstanbul, Türkiye"
    assert "İstanbul, Türkiye" in results[0].outreach_message
