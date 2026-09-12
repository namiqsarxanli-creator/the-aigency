import json

from app import sales_intelligence
from app.db_models import SalesLead, Workspace


class FakeResponse:
    status_code = 200
    ok = True
    url = "https://example.test/"
    text = """<!doctype html><html lang="az"><head>
      <title>Premium restoran və rezervasiya xidməti Bakı</title>
      <meta name="description" content="Bakıda premium restoran, xüsusi menyu, rahat rezervasiya və qonaqlar üçün yüksək səviyyəli xidmət təqdim edirik.">
      <meta name="viewport" content="width=device-width"><link rel="canonical" href="https://example.test/">
      <meta property="og:title" content="Restoran"><script>gtag('config','G-TEST')</script>
      </head><body><h1>Premium restoran</h1><h2>Menyu</h2><h2>Haqqımızda</h2>
      <p>Biz sizə rahat rezervasiya, keyfiyyətli menyu və nəticə təqdim edirik.</p>
      <a href="tel:+994000000000">Zəng</a><a href="https://wa.me/994000000000">WhatsApp</a>
      <form><label>Ad <input></label></form><p>review testimonial privacy instagram Bakı</p>
      <img src="a.jpg" alt="Restoran zalı"></body></html>"""
    content = text.encode()

    def raise_for_status(self):
        return None


def test_detailed_audit_has_sections_evidence_and_action_plan(db, monkeypatch):
    monkeypatch.setattr(sales_intelligence.requests, "get", lambda *a, **k: FakeResponse())
    workspace = Workspace(name="Audit", slug="audit")
    db.add(workspace); db.flush()
    lead = SalesLead(workspace_id=workspace.id, company_name="Test Restoran", category="restaurant",
                     city="Bakı", address="Nizami 1", website="https://example.test/",
                     phone="+994000000000", email="info@example.test", source_external_id="audit-1")
    db.add(lead); db.commit()

    audit = sales_intelligence.audit_lead(db, lead)
    details = json.loads(audit.details_json)

    assert len(details["sections"]) == 8
    assert sum(item["max"] for item in details["sections"]) == 100
    assert len(details["action_plan"]) == 7
    assert details["evidence"]["h1_count"] == 1
    assert details["evidence"]["forms"] == 1
    # Mətn müştəri dilinə keçirilib (bax: tests/test_audit_language.py) — xülasə şirkət adı ilə
    # başlayır və balı "100 baldan N" formatında, texniki termin olmadan verir.
    assert audit.summary.startswith("Test Restoran üçün saytın 8 istiqamət")
    assert "100 baldan" in audit.summary

    proposal = sales_intelligence.create_proposal(db, workspace.id, lead, audit, language="EN")
    assert proposal.language == "EN"
    assert "7 days" in proposal.solution
    assert "out of 100" in proposal.problem
