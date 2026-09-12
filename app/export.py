"""Layihənin müştəriyə təhvil paketi — çap-hazır hesabat (PDF) və ZIP arxiv.

NİYƏ PDF KİTABXANASI YOX: reportlab/fpdf kimi kitabxanalar Azərbaycan hərflərini (ə, ğ, ı, ş)
yalnız ayrıca Unicode TTF şrifti daxil edildikdə düzgün göstərir — bu, layihəyə həm ağır
asılılıq, həm də şrift faylı gətirir. Bunun əvəzinə ÇAP-HAZIR HTML qaytarırıq: brauzerin
"Çap et → PDF kimi saxla" funksiyası eyni nəticəni verir, bütün hərflər mükəmməl çıxır və
heç bir yeni asılılıq lazım deyil.
"""
import html
import io
import re
import zipfile
import csv
from datetime import datetime

from sqlalchemy.orm import Session

from .db_models import AgentProject, AgentTask, Campaign, ContentAsset

ROLE_LABELS = {
    "strategist": "Strategiya", "copywriter": "Mətn (kopirayter)", "designer": "Vizual",
    "developer": "Developer (HTML)", "sales_strategist": "Satış strategiyası",
    "outreach_writer": "Satış mətnləri", "marketing": "Marketinq planı",
    "analytics": "Analitika / KPI", "legal": "Hüquq və uyğunluq", "finance": "Büdcə və qiymət",
}
# Fayl adlarında departament sırası qorunsun deyə nömrələnir.
ROLE_ORDER = list(ROLE_LABELS)


def _slug(text: str, limit: int = 40) -> str:
    """Fayl adı üçün təhlükəsiz sətir (ASCII-ə yaxın, boşluqsuz)."""
    table = str.maketrans("əğıöüçşİıĞÖÜÇŞƏ", "agioucsIiGOUCSA")
    clean = (text or "").translate(table)
    clean = re.sub(r"[^A-Za-z0-9]+", "-", clean).strip("-").lower()
    return (clean[:limit] or "layihe").strip("-")


def collect_bundle(db: Session, project: AgentProject) -> dict:
    """Layihənin bütün materiallarını bir yerə yığır (hesabat və ZIP üçün ortaq mənbə)."""
    tasks = (
        db.query(AgentTask)
        .filter(AgentTask.project_id == project.id)
        .order_by(AgentTask.order_index)
        .all()
    )
    sections = []
    for task in tasks:
        output = (task.output or "").strip()
        if not output or task.role not in ROLE_LABELS:
            continue
        # DİQQƏT (dizayner şəkli): `task.output` generasiya ANINDA seçilmiş şəkildir — layihə
        # sonradan yenidən şəkilləndirilsə (məs. Studio+ ilə brend palitrasına uyğun yeni şəkil
        # yaradılıb `project.deliverable_image_url`-ə yazılsa) bu köhnə URL DƏYİŞMİR. Nəticədə
        # hesabatda saytda göstərilən şəkildən FƏRQLİ bir şəkil çıxırdı (canlı sınaqda tapıldı —
        # layihə #36). `deliverable_image_url` yeganə həqiqi mənbədir (Instagram paylaşımı da
        # elə oradan gedir), ona görə varsa dizayner sətri ona üstünlük verilir.
        image_output = (
            project.deliverable_image_url if task.role == "designer" and project.deliverable_image_url
            else output
        )
        sections.append({
            "role": task.role,
            "label": ROLE_LABELS[task.role],
            "title": task.title,
            "output": image_output,
            "revision_count": task.revision_count or 0,
            "is_image": task.role == "designer",
        })
    campaign = (
        db.query(Campaign)
        .filter(Campaign.source_project_id == project.id)
        .order_by(Campaign.id.desc())
        .first()
    )
    days = list(campaign.days) if campaign else []
    day_ids = [day.id for day in days]
    assets = (
        db.query(ContentAsset).filter(ContentAsset.campaign_day_id.in_(day_ids)).all()
        if day_ids else []
    )
    assets_by_day = {asset.campaign_day_id: asset for asset in assets}
    return {
        "project": project,
        "sections": sections,
        "campaign": campaign,
        "campaign_days": days,
        "assets_by_day": assets_by_day,
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }


def _social_plan_text(bundle: dict) -> str:
    """Müştərinin icra edə biləcəyi oxunaqlı 7 günlük paylaşım planı."""
    days = bundle.get("campaign_days") or []
    assets = bundle.get("assets_by_day") or {}
    if not days:
        marketing = next((s["output"] for s in bundle["sections"] if s["role"] == "marketing"), "")
        return "7 GÜNLÜK PAYLAŞIM PLANI\n\n" + (marketing or "Kampaniya təqvimi hələ yaradılmayıb.") + "\n"
    lines = ["7 GÜNLÜK PAYLAŞIM PLANI", "=" * 46, ""]
    for day in days:
        asset = assets.get(day.id)
        date_text = day.planned_date.strftime("%d.%m.%Y") if day.planned_date else "Tarix təyin edilməyib"
        lines.extend([
            f"GÜN {day.day_number} · {date_text}",
            f"Platforma: {day.platform}",
            f"Format: {day.content_type}",
            f"Mövzu: {day.theme}",
            f"Hook: {day.hook or '—'}",
            f"CTA: {day.cta or '—'}",
            f"Caption: {(asset.caption if asset and asset.caption else 'Hazırlanmayıb')}",
            f"Vizual istiqamət: {(asset.visual_brief if asset and asset.visual_brief else 'Hazırlanmayıb')}",
            f"Status: {(asset.status if asset else day.status)}",
            "",
        ])
    return "\n".join(lines)


def _social_calendar_csv(bundle: dict) -> str:
    """Excel/Google Sheets-də açılan UTF-8 kontent təqvimi."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Gün", "Tarix", "Saat", "Platforma", "Format", "Mövzu", "Hook", "CTA", "Caption", "Vizual", "Status"])
    assets = bundle.get("assets_by_day") or {}
    for day in bundle.get("campaign_days") or []:
        asset = assets.get(day.id)
        writer.writerow([
            day.day_number,
            day.planned_date.isoformat() if day.planned_date else "",
            "",  # Kampaniyada saat sahəsi yoxdur; uydurmaq əvəzinə müştərinin seçimi üçün boş saxlanır.
            day.platform, day.content_type, day.theme, day.hook or "", day.cta or "",
            asset.caption if asset and asset.caption else "",
            asset.visual_brief if asset and asset.visual_brief else "",
            asset.status if asset else day.status,
        ])
    # Excel-in UTF-8-i səhvsiz tanıması üçün BOM.
    return "\ufeff" + output.getvalue()


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE = re.compile(r"^[-*•]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")


def _rich_text(raw: str) -> str:
    """Agent çıxışındakı sadə markdown-ı (qalın mətn, siyahılar) HTML-ə çevirir.

    NİYƏ: agentlər markdown yazır (`**Başlıq**`, `- maddə`), hesabat isə mətni `<pre>` içində
    OLDUĞU KİMİ göstərirdi — müştəri PDF-də xam `**` ulduzlarını görürdü (canlı tapıntı).
    Tam markdown kitabxanası gətirmək bu qədər sadə format üçün artıqdır.

    TƏHLÜKƏSİZLİK: əvvəlcə `html.escape` tətbiq olunur, HTML teqləri YALNIZ ondan sonra
    əlavə edilir — agent çıxışındakı `<script>` kimi mətn heç vaxt icra oluna bilməz."""
    blocks: list[str] = []
    items: list[str] = []
    list_tag = ""
    paragraph: list[str] = []

    def flush_list() -> None:
        nonlocal items, list_tag
        if items:
            blocks.append(f"<{list_tag}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{list_tag}>")
            items, list_tag = [], ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append("<p>" + "<br>".join(paragraph) + "</p>")
            paragraph = []

    for line in html.escape(raw).splitlines():
        stripped = line.strip()
        if not stripped:
            flush_list(); flush_paragraph()
            continue
        bullet = _BULLET_RE.match(stripped)
        numbered = _NUMBERED_RE.match(stripped)
        if bullet or numbered:
            tag = "ul" if bullet else "ol"
            if list_tag and list_tag != tag:
                flush_list()
            flush_paragraph()
            list_tag = tag
            items.append(_BOLD_RE.sub(r"<strong>\1</strong>", (bullet or numbered).group(1)))
        else:
            flush_list()
            paragraph.append(_BOLD_RE.sub(r"<strong>\1</strong>", stripped))
    flush_list(); flush_paragraph()
    return "".join(blocks)


def render_report_html(bundle: dict, workspace_name: str = "") -> str:
    """Çap-hazır, tam müstəqil (external asset-siz) HTML hesabat.

    Brauzerdə açılanda avtomatik çap dialoqu təklif edir — istifadəçi "PDF kimi saxla" seçir.
    Bütün stil daxildədir ki, fayl offline saxlanılanda da eyni görünsün."""
    project = bundle["project"]
    esc = html.escape

    blocks = []
    for index, section in enumerate(bundle["sections"], start=1):
        if section["is_image"]:
            body = (
                f'<img src="{esc(section["output"])}" alt="Vizual" class="visual">'
                f'<p class="src">Mənbə: <span>{esc(section["output"])}</span></p>'
            )
        elif section["role"] == "developer":
            # HTML kodunu göstəririk (icra etmirik) — müştəri kodu görüb developerinə verə bilsin.
            body = f'<pre class="code">{esc(section["output"])}</pre>'
        else:
            body = f'<div class="prose">{_rich_text(section["output"])}</div>'
        revised = (
            f'<span class="rev">{section["revision_count"]} dəfə yenidən yazılıb</span>'
            if section["revision_count"] else ""
        )
        blocks.append(
            f'<section class="block"><h2><i>{index:02d}</i>{esc(section["label"])}{revised}</h2>'
            f'<h3>{esc(section["title"])}</h3>{body}</section>'
        )

    status_labels = {
        "AWAITING_APPROVAL": "Təsdiq gözləyir", "DELIVERED": "Təhvil verilib",
        "REJECTED": "Rədd edilib", "IN_PROGRESS": "İşlənir", "BRIEF": "Planlaşdırılır",
    }
    return f"""<!doctype html>
<html lang="az"><head><meta charset="utf-8">
<title>Layihə #{project.id} — hesabat</title>
<style>
  @page {{ margin: 18mm 16mm; }}
  *{{box-sizing:border-box}}
  body{{margin:0;font:13px/1.7 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#16130f;background:#fff}}
  .sheet{{max-width:860px;margin:auto;padding:34px 30px 60px}}
  .head{{border-bottom:3px solid #16130f;padding-bottom:22px;margin-bottom:30px}}
  .eyebrow{{font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#8a7a55}}
  h1{{font:italic 34px/1.15 Georgia,serif;margin:10px 0 14px}}
  .meta{{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:11px;color:#6b6459}}
  .meta b{{color:#16130f;font-weight:600}}
  .brief{{background:#f6f3ec;border-left:3px solid #b99a5b;padding:15px 18px;margin:24px 0 34px;font-size:13px}}
  .brief small{{display:block;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:#8a7a55;margin-bottom:7px}}
  .block{{margin-bottom:30px;page-break-inside:avoid}}
  h2{{font:19px Georgia,serif;margin:0 0 4px;display:flex;align-items:baseline;gap:11px;border-bottom:1px solid #ddd6c8;padding-bottom:8px}}
  h2 i{{font-style:normal;font-size:11px;color:#b99a5b;letter-spacing:.1em}}
  h3{{font-size:11px;font-weight:600;color:#6b6459;margin:9px 0 11px;letter-spacing:.04em}}
  .rev{{margin-left:auto;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#a08a5c;font-family:inherit}}
  /* `font:12.5px/1.72 inherit` yazılmışdı — `font` QISAYOLUNDA `inherit` etibarsız ailə adıdır,
     brauzer bütün bəyanatı ataraq <pre>-nin öz default MONOSPACE şriftinə qayıdırdı və hesabat
     kod kimi görünürdü (canlı tapıntı). Ayrı-ayrı xassələr etibarlıdır. */
  pre{{margin:0;white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:12.5px;line-height:1.72}}
  pre.code{{background:#f6f3ec;padding:14px;font-family:Consolas,monospace;font-size:11px;line-height:1.6;overflow-x:auto}}
  .prose{{font-size:13px;line-height:1.75}}
  .prose p{{margin:0 0 11px}}
  .prose ul,.prose ol{{margin:0 0 12px;padding-left:22px}}
  .prose li{{margin:0 0 5px}}
  .prose strong{{font-weight:600;color:#16130f}}
  .visual{{max-width:100%;border:1px solid #ddd6c8}}
  .src{{font-size:10px;color:#8b8377;word-break:break-all;margin:7px 0 0}}
  .foot{{margin-top:44px;border-top:1px solid #ddd6c8;padding-top:16px;font-size:10px;color:#8b8377;display:flex;justify-content:space-between;gap:16px}}
  .printbar{{position:sticky;top:0;background:#16130f;color:#fff;padding:11px 16px;display:flex;justify-content:space-between;align-items:center;gap:14px;font-size:12px}}
  .printbar button{{background:#d8ff5f;color:#16130f;border:0;padding:9px 16px;font-weight:700;cursor:pointer;font-size:12px}}
  @media print {{ .printbar{{display:none}} .sheet{{padding:0}} }}
</style></head><body>
<div class="printbar">
  <span>Bu səhifəni PDF kimi saxlamaq üçün "Çap et" düyməsinə basın → Hədəf: <b>PDF kimi saxla</b></span>
  <button onclick="window.print()">🖨 Çap et / PDF</button>
</div>
<div class="sheet">
  <header class="head">
    <div class="eyebrow">{esc(workspace_name or "The Aigency")} · Layihə hesabatı</div>
    <h1>Layihə #{project.id}</h1>
    <div class="meta">
      <span><b>Status:</b> {esc(status_labels.get(project.status, project.status))}</span>
      <span><b>Format:</b> {esc("Sosial post" if project.output_type == "social_post" else "Landing page")}</span>
      <span><b>Yaradılıb:</b> {project.created_at.strftime("%d.%m.%Y") if project.created_at else "—"}</span>
      <span><b>Hesabat tarixi:</b> {bundle["generated_at"]}</span>
    </div>
  </header>
  <div class="brief"><small>Müştəri brifi</small>{esc(project.brief)}</div>
  {"".join(blocks) or "<p>Bu layihədə hələ hazır material yoxdur.</p>"}
  <div class="foot">
    <span>The Aigency — avtonom yaradıcı studiya</span>
    <span>Layihə #{project.id} · {bundle["generated_at"]}</span>
  </div>
</div>
</body></html>"""


def build_zip(bundle: dict) -> bytes:
    """Bütün materialları ayrı-ayrı fayllar kimi ZIP arxivə yığır."""
    project = bundle["project"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "00-brif.txt",
            f"LAYIHƏ #{project.id}\nStatus: {project.status}\n"
            f"Hesabat: {bundle['generated_at']}\n\n--- MÜŞTƏRİ BRİFİ ---\n{project.brief}\n",
        )
        is_social = project.output_type == "social_post"
        for section in bundle["sections"]:
            # Sosial media müştərisinə xam Developer/HTML hesabatı lazım deyil. Texniki
            # nəticə yalnız landing-page paketində saxlanılır.
            if is_social and section["role"] == "developer":
                continue
            order = ROLE_ORDER.index(section["role"]) + 1
            name = f"{order:02d}-{_slug(section['label'])}.txt"
            header = f"{section['label'].upper()}\n{section['title']}\n{'=' * 46}\n\n"
            archive.writestr(name, header + section["output"] + "\n")

        if is_social:
            archive.writestr("02-7-gunluk-paylasim-plani.txt", _social_plan_text(bundle))
            archive.writestr("03-kontent-teqvimi.csv", _social_calendar_csv(bundle))
            copy = next((s["output"] for s in bundle["sections"] if s["role"] == "copywriter"), "")
            analytics = next((s["output"] for s in bundle["sections"] if s["role"] == "analytics"), "")
            archive.writestr("04-caption-ve-mesajlar.txt", copy or "Caption materialı hələ hazırlanmayıb.\n")
            archive.writestr("05-olcme-plani.txt", analytics or "Ölçmə planı hələ hazırlanmayıb.\n")

        if project.deliverable_html:
            if project.output_type == "social_post":
                archive.writestr("deliverable-post.txt", project.deliverable_html)
            else:
                archive.writestr("deliverable-landing-page.html", project.deliverable_html)
        if project.deliverable_image_url:
            archive.writestr("vizual-link.txt", project.deliverable_image_url + "\n")
        # Şəkil URL kimi saxlanılır (bayt kimi yox) — arxiv yüngül qalsın və mənbə hüququ aydın olsun.
        archive.writestr(
            "OXU-MENI.txt",
            "Bu arxiv The Aigency tərəfindən hazırlanmış layihə materiallarıdır.\n\n"
            "  00-brif.txt ................ müştəri brifi\n"
            "  01..10-*.txt ............... layihəyə uyğun departament materialları\n"
            "  02-7-gunluk-*.txt .......... sosial layihələr üçün gündəlik paylaşım planı\n"
            "  03-kontent-teqvimi.csv ..... tarix, platforma, format, CTA və status\n"
            "  deliverable-* .............. son məhsul (landing page HTML və ya post mətni)\n"
            "  vizual-link.txt ............ istifadə olunan şəklin ünvanı\n\n"
            "PDF hesabat üçün saytda 'PDF hesabat' düyməsindən istifadə edin.\n",
        )
    return buffer.getvalue()


def zip_filename(project: AgentProject) -> str:
    return f"layihe-{project.id}-{_slug(project.brief, 30)}.zip"
