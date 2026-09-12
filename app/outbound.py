"""Human-approved email outbox. No credentials means safe no-send mode."""
import smtplib
from datetime import datetime
from email.message import EmailMessage

from app.core import settings
from app.db_models import OutboundDelivery
from app.factory import get_control, is_enabled


def smtp_ready() -> bool:
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_from_email)


def external_delivery_enabled() -> bool:
    # Sosial paylaşımın açılması heç vaxt email göndərişinə icazə vermir.
    return bool(settings.email_delivery_enabled and smtp_ready())


def process_outbox(db) -> int:
    if not external_delivery_enabled():
        return 0
    due = db.query(OutboundDelivery).filter(
        OutboundDelivery.status == "QUEUED", OutboundDelivery.scheduled_at <= datetime.utcnow()
    ).limit(10).all()
    sent = 0
    for delivery in due:
        if not is_enabled(db, delivery.workspace_id, "outbound_enabled"):
            continue
        control = get_control(db, delivery.workspace_id)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = db.query(OutboundDelivery).filter(
            OutboundDelivery.workspace_id == delivery.workspace_id,
            OutboundDelivery.status == "SENT", OutboundDelivery.sent_at >= today,
        ).count()
        if sent_today >= control.daily_email_limit:
            continue
        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = delivery.recipient
        message["Subject"] = delivery.activity.subject or "Qısa təklif"
        message.set_content(delivery.activity.content)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls: smtp.starttls()
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
            delivery.status = "SENT"; delivery.sent_at = datetime.utcnow(); delivery.activity.status = "SENT"
            delivery.lead.status = "CONTACTED"; sent += 1
        except Exception as exc:
            delivery.status = "FAILED"; delivery.error = str(exc)[:1000]
        db.commit()
    return sent
