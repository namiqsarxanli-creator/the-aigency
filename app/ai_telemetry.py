"""AI xərc təxmini və workspace üzrə gündəlik büdcə qapısı."""
from datetime import datetime, timezone

from app.database import SessionLocal
from app.db_models import FactoryControl, LlmUsage

# USD per 1M tokens. Estimates are intentionally centralized and can be updated independently.
MODEL_PRICES = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}


def estimate_cost_microusd(model: str, input_tokens: int, output_tokens: int) -> int:
    input_price, output_price = MODEL_PRICES.get(model, (0.0, 0.0))
    usd = input_tokens / 1_000_000 * input_price + output_tokens / 1_000_000 * output_price
    return round(usd * 1_000_000)


def budget_available(workspace_id: int | None) -> bool:
    """Limit dolubsa False qaytarır; DB xətasında xərc təhlükəsizliyi üçün bağlı qalır."""
    if not workspace_id:
        return True
    db = SessionLocal()
    try:
        control = db.query(FactoryControl).filter(FactoryControl.workspace_id == workspace_id).first()
        if not control or control.daily_api_budget_cents <= 0:
            return False if control else True
        today = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
        rows = db.query(LlmUsage.model, LlmUsage.prompt_tokens, LlmUsage.completion_tokens).filter(
            LlmUsage.workspace_id == workspace_id, LlmUsage.created_at >= today, LlmUsage.ok.is_(True),
        ).all()
        spent = sum(estimate_cost_microusd(model or "", prompt or 0, completion or 0)
                    for model, prompt, completion in rows)
        return spent < control.daily_api_budget_cents * 10_000
    except Exception:
        return False
    finally:
        db.close()
