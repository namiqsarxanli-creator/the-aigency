from app import outbound


class ExplodingDb:
    def query(self, *_args, **_kwargs):
        raise AssertionError("Dry-run rejimində outbox DB-dən belə oxunmamalıdır")


def test_external_delivery_is_hard_blocked_by_default(monkeypatch):
    monkeypatch.setattr(outbound.settings, "email_delivery_enabled", False)
    monkeypatch.setattr(outbound.settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(outbound.settings, "smtp_username", "configured")
    monkeypatch.setattr(outbound.settings, "smtp_password", "configured")
    monkeypatch.setattr(outbound.settings, "smtp_from_email", "agency@example.test")
    assert outbound.smtp_ready() is True
    assert outbound.external_delivery_enabled() is False
    assert outbound.process_outbox(ExplodingDb()) == 0
