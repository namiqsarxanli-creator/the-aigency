"""Prompt sağlamlığı — əvvəl canlı istifadədə tapılmış konkret səhvlərin qoruyucusu.

TARİXÇƏ: dəstək rollarının hamısına verilən ortaq "giriş cümləsi yazma" qaydasında HÜQUQ
bölməsinə xas KONKRET NÜMUNƏ mətni var idi. Zəif modellər öz məzmununu yazmaq əvəzinə həmin
nümunəni papağayı kimi təkrarlayırdı — nəticədə Satış Strateqi və Analitika hesabatları
hüquq mətni ilə başlayırdı. Bu testlər həmin səhvin geri qayıtmasının qarşısını alır.
"""
import re

from app import agency

SUPPORT_PROMPTS = {
    "sales_strategist": agency.SALES_STRATEGIST_SYSTEM,
    "outreach_writer": agency.OUTREACH_WRITER_SYSTEM,
    "marketing": agency.MARKETING_SYSTEM,
    "analytics": agency.ANALYTICS_SYSTEM,
}


def test_all_support_roles_have_the_no_preamble_rule():
    for role, prompt in SUPPORT_PROMPTS.items():
        assert agency._NO_PREAMBLE_RULE in prompt, f"{role} promptunda format qaydası yoxdur"


def test_shared_rule_contains_no_domain_specific_example():
    """Ortaq qaydada HEÇ BİR konkret başlıq nümunəsi olmamalıdır — zəif modellər onu
    öz məzmunu kimi kopyalayır (məhz bu, canlı sistemdə üzə çıxan bug idi)."""
    forbidden = ["RİSKLİ İDDİA", "QİYMƏT STRATEGİYASI", "ƏSAS KPI", "HƏDƏF MÜŞTƏRİ"]
    for phrase in forbidden:
        assert phrase not in agency._NO_PREAMBLE_RULE, (
            f"Ortaq qaydada konkret nümunə var: {phrase!r} — modellər bunu təkrarlayır"
        )


def test_every_role_has_a_system_prompt():
    """`_run_role` rolu `system_map`-də tapmasa KeyError atıb boru xəttini dayandırar."""
    for role in agency.ROLE_SEQUENCE:
        assert role in agency.ROLE_LABELS, f"{role} üçün etiket yoxdur"


def test_role_sequence_has_no_duplicates():
    assert len(agency.ROLE_SEQUENCE) == len(set(agency.ROLE_SEQUENCE))


def test_removed_departments_are_not_scheduled():
    assert "legal" not in agency.ROLE_SEQUENCE
    assert "finance" not in agency.ROLE_SEQUENCE
    assert "legal" not in agency.SOCIAL_SUPPORT_SEQUENCE
    assert "finance" not in agency.SOCIAL_SUPPORT_SEQUENCE


def test_support_dependencies_reference_known_roles():
    for role, deps in agency.SUPPORT_DEPS.items():
        assert role in agency.ROLE_SEQUENCE
        for dep in deps:
            assert dep in agency.ROLE_SEQUENCE, f"{role} tanınmayan {dep} rolundan asılıdır"


def test_designer_prompt_detection_rejects_azerbaijani_text():
    """Dizaynerdən İNGİLİSCƏ axtarış sözləri gözlənilir — Azərbaycanca cavab şəkil axtarışı
    üçün yararsızdır və mövzuya yad şəkil gətirir."""
    assert agency._usable_image_prompt("modern coffee shop minimal interior") is True
    assert agency._usable_image_prompt("Brifə uyğun dizayner işini gör") is False
    assert agency._usable_image_prompt("") is False
    assert agency._usable_image_prompt(None) is False


def test_retry_seconds_parsed_from_groq_message():
    """Groq gözləmə müddətini başlıqda yox, JSON mətnində göndərir."""
    class _Response:
        headers = {}
        text = '{"error":{"message":"Rate limit reached. Please try again in 6.45s."}}'

    assert agency._parse_retry_seconds(_Response()) == 6.45


def test_retry_seconds_prefers_retry_after_header():
    class _Response:
        headers = {"retry-after": "12"}
        text = "try again in 99s"

    assert agency._parse_retry_seconds(_Response()) == 12.0


def test_extract_json_handles_code_fences():
    """LLM cavabı ```json ... ``` içinə bükməyi sevir — planlaşdırma bundan asılıdır."""
    assert agency._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert agency._extract_json('Budur: {"a": 2} — bu qədər') == {"a": 2}
    assert agency._extract_json("heç bir json yoxdur") is None
