"""Pydantic sxemləri — API request/response formaları."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BriefRequest(BaseModel):
    brief: str = Field(..., min_length=5, max_length=2000)
    # Telegram-dan yaradılan briflərdə n8n bunu göndərir ki, nəticə hazır olanda
    # kimə bildiriş edəcəyimizi bilək (web dashboard-dan yaradılanlarda boş qalır).
    # Telegram-ın chat.id-si ədəddir, n8n da onu JSON number kimi göndərir (yəni
    # 123456789, "123456789" yox) — Pydantic v2 int-i avtomatik str-ə
    # çevirmədiyi üçün əvvəllər 422 xətası verirdi, ona görə burda özümüz çeviririk.
    telegram_chat_id: Optional[str] = None

    @field_validator("telegram_chat_id", mode="before")
    @classmethod
    def _stringify_chat_id(cls, v):
        return str(v) if v is not None else v


class TaskOut(BaseModel):
    id: int
    role: str
    title: str
    description: Optional[str] = None
    status: str
    output: Optional[str] = None
    revision_count: int

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    from_role: str
    to_role: Optional[str] = None
    kind: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: int
    brief: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectDetail(ProjectOut):
    output_type: str = "landing_page"
    deliverable_html: Optional[str] = None
    deliverable_image_url: Optional[str] = None
    sales_kit: Optional[str] = None
    reject_feedback: Optional[str] = None
    retry_of_id: Optional[int] = None
    instagram_published: bool = False
    instagram_permalink: Optional[str] = None
    # Bu workspace-ə Instagram hesabı qoşulubmu (əlavə ödənişli paket). False olanda UI
    # "Paylaş" düyməsi ƏVƏZİNƏ paket təklifi göstərir — əks halda müştəri işləməyəcək
    # (və ya səhv hesaba gedəcək) düyməyə basardı.
    instagram_available: bool = False
    tasks: list[TaskOut] = []
    messages: list[MessageOut] = []


class RunResult(BaseModel):
    status: str
    steps: int


class RejectRequest(BaseModel):
    # İxtiyari — verilsə, komanda NİYƏ rədd edildiyini bilib avtomatik yeni cəhdə başlayır.
    reason: Optional[str] = Field(default=None, max_length=1000)


class RejectResult(ProjectOut):
    retry_project_id: Optional[int] = None


class InstagramPublishResult(BaseModel):
    ok: bool
    post_id: Optional[str] = None
    permalink: Optional[str] = None
    detail: Optional[str] = None


class RegenerateRequest(BaseModel):
    """Tək bir departamentin işini yenidən yazdırmaq. `instruction` — nəyin dəyişməsini istəyirsən."""
    instruction: Optional[str] = Field(default=None, max_length=1000)


class TaskVersionOut(BaseModel):
    version_no: int
    output: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TaskVersionsResult(BaseModel):
    task_id: int
    role: str
    title: str
    current_output: Optional[str] = None
    # Ən yeni arxiv əvvəldə. Cari (canlı) çıxış burada YOXDUR — o, `current_output`-dadır.
    versions: list[TaskVersionOut] = []


class UsageRow(BaseModel):
    label: str
    calls: int
    ok_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    avg_latency_ms: int


class UsageReport(BaseModel):
    has_data: bool
    total_calls: int
    total_tokens: int
    failed_calls: int
    by_provider: list[UsageRow] = []
    by_role: list[UsageRow] = []
    failures: dict[str, int] = {}


class PendingProjectOut(BaseModel):
    """Telegram/n8n bildiriş axını üçün — hələ bildirilməmiş, təsdiq gözləyən layihələr."""
    id: int
    brief: str
    output_type: str = "landing_page"
    deliverable_html: Optional[str] = None
    deliverable_image_url: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # Müştəriyə göndərilə bilən ictimai nəticə linki — n8n bunu Telegram bildirişinə əlavə edir.
    view_url: str

    class Config:
        from_attributes = True
