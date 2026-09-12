from collections import defaultdict

from sqlalchemy.orm import Session

from .db_models import CampaignMetric


def _ratio(part: int, whole: int) -> float:
    return round((part / whole * 100), 1) if whole else 0.0


def _summary(rows):
    totals = {
        "impressions": sum(row.impressions for row in rows),
        "reach": sum(row.reach for row in rows),
        "engagements": sum(row.engagements for row in rows),
        "clicks": sum(row.clicks for row in rows),
        "leads": sum(row.leads for row in rows),
        "sales": sum(row.sales for row in rows),
        "spend_cents": sum(row.spend_cents for row in rows),
        "revenue_cents": sum(row.revenue_cents for row in rows),
    }
    totals.update(
        engagement_rate=_ratio(totals["engagements"], totals["reach"]),
        ctr=_ratio(totals["clicks"], totals["impressions"]),
        lead_conversion=_ratio(totals["leads"], totals["clicks"]),
        sales_conversion=_ratio(totals["sales"], totals["leads"]),
        spend=totals["spend_cents"] / 100,
        revenue=totals["revenue_cents"] / 100,
        roas=round(totals["revenue_cents"] / totals["spend_cents"], 2)
        if totals["spend_cents"]
        else 0.0,
    )
    return totals


def build_analytics(db: Session, workspace_id: int, campaign_id: int | None = None):
    query = db.query(CampaignMetric).filter(CampaignMetric.workspace_id == workspace_id)
    if campaign_id:
        query = query.filter(CampaignMetric.campaign_id == campaign_id)
    rows = query.order_by(CampaignMetric.recorded_date.asc()).all()
    totals = _summary(rows)

    grouped = defaultdict(list)
    dated = defaultdict(lambda: {"reach": 0, "engagements": 0, "revenue": 0})
    for row in rows:
        grouped[row.platform].append(row)
        day = dated[row.recorded_date]
        day["reach"] += row.reach
        day["engagements"] += row.engagements
        day["revenue"] += row.revenue_cents

    platforms = []
    for platform, platform_rows in grouped.items():
        item = _summary(platform_rows)
        item["name"] = platform
        platforms.append(item)
    platforms.sort(key=lambda item: (item["revenue_cents"], item["leads"]), reverse=True)

    trend = []
    # Yeni dərc edilmiş postun ilk insight snapshot-u çox vaxt bütünlüklə 0 olur.
    # Sətir mövcud olduğu üçün max(..., default=1) kömək etmir və aşağıda 0-a bölünür.
    max_reach = max(1, max((value["reach"] for value in dated.values()), default=0))
    for day, value in sorted(dated.items()):
        trend.append({
            "label": day.strftime("%d %b"),
            "reach": value["reach"],
            "engagements": value["engagements"],
            "revenue": value["revenue"] / 100,
            "height": max(8, round(value["reach"] / max_reach * 100)),
        })

    recommendations = []
    if not rows:
        recommendations.append("İlk nəticələri əlavə edin; panel kampaniya və platforma üzrə qərar siqnallarını avtomatik hesablayacaq.")
    else:
        if platforms:
            recommendations.append(f"{platforms[0]['name']} hazırda ən güclü kanaldır. Növbəti test büdcəsinin 15–20%-ni bu kanala yönəldin.")
        if totals["ctr"] < 1.5:
            recommendations.append("Klik faizi zəifdir. İlk 2 saniyəlik hook və əsas vizual üçün iki yeni variant test edin.")
        if totals["clicks"] and totals["lead_conversion"] < 10:
            recommendations.append("Trafik gəlir, lakin lead-ə çevrilmə aşağıdır. Təklif, CTA və açılış səhifəsinin uyğunluğunu gücləndirin.")
        if totals["spend_cents"] and totals["roas"] < 1:
            recommendations.append("ROAS 1-dən aşağıdır. Zəif reklam setlərini dayandırıb büdcəni nəticə verən kreativlərə keçirin.")
        if len(recommendations) == 1:
            recommendations.append("Nəticələr sağlam görünür. Qalib kreativi saxlayaraq auditoriya və format üzrə kontrollu testə davam edin.")

    return {
        "has_data": bool(rows),
        "totals": totals,
        "platforms": platforms,
        "trend": trend[-14:],
        "recommendations": recommendations,
    }
