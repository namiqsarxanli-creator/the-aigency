(function () {
  "use strict";
  const questions = [
    { key: "company", text: "Salam! Mən Brif köməkçisiyəm. Şirkətinizin adını və fəaliyyət sahəsini qısa yazın." },
    { key: "offer", text: "Əsas məhsul və ya xidmətiniz nədir? Müştəri niyə məhz sizi seçməlidir?" },
    { key: "audience", text: "Hədəf auditoriyanız kimdir, haradadır və əsas ehtiyacı nədir?" },
    { key: "goal", text: "Bu işin biznes məqsədi nədir: satış, müraciət, tanınma, yoxsa təqdimat?" },
    { key: "deliverable", text: "Hansı nəticəni istəyirsiniz: post, 7 günlük kampaniya, landing page, reklam mətni, yoxsa tam paket?" },
    { key: "tone", text: "Vizual üslub və ünsiyyət tonu necə olsun? Nümunə və rəngləri də qeyd edə bilərsiniz." },
    { key: "requirements", text: "Mütləq istifadə olunmalı məlumat, CTA, dil, platforma və son tarix varmı?" },
    { key: "avoid", text: "Nələrdən qaçmalıyıq? Qadağan söz, uyğun olmayan üslub və ya hüquqi məhdudiyyətləri yazın." }
  ];
  let step = 0, answers = {};
  function node(tag, cls, text) { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; }
  const fab = node("button", "brief-bot-fab"); fab.type = "button"; fab.setAttribute("aria-label", "Brif köməkçisini aç"); fab.append(node("i", "", "✦"), node("span", "", "Brif köməkçisi"));
  const panel = node("section", "brief-bot-panel"); panel.hidden = true;
  panel.innerHTML = '<header class="brief-bot-head"><div><b>Brif köməkçisi</b><small>8 addımda peşəkar prompt</small></div><button class="brief-bot-close" type="button" aria-label="Bağla">✕</button></header><div class="brief-bot-progress"><i></i></div><div class="brief-bot-log" aria-live="polite"></div><div class="brief-bot-actions" hidden></div><div class="brief-bot-controls"><input class="brief-bot-input" maxlength="700" placeholder="Cavabınızı yazın…"><button class="brief-bot-send" type="button">Göndər</button></div><div class="brief-bot-note">Cavablar yalnız bu brauzerdə saxlanır; siz təsdiqləmədən layihə başladılmır.</div>';
  document.body.append(fab, panel);
  const log = panel.querySelector(".brief-bot-log"), input = panel.querySelector(".brief-bot-input"), actions = panel.querySelector(".brief-bot-actions"), controls = panel.querySelector(".brief-bot-controls"), progress = panel.querySelector(".brief-bot-progress i");
  function message(role, text) { const bubble = node("div", "brief-bot-msg brief-bot-" + role, text); log.appendChild(bubble); log.scrollTop = log.scrollHeight; }
  function ask() { progress.style.width = Math.round(step / questions.length * 100) + "%"; message("agent", questions[step].text); input.placeholder = (step + 1) + "/" + questions.length + " · Cavabınızı yazın…"; input.focus(); }
  function buildBrief() {
    return ["Aşağıdakı biznes üçün peşəkar yaradıcı iş hazırlayın.", "", "ŞİRKƏT VƏ SAHƏ\n" + answers.company, "", "MƏHSUL / XİDMƏT VƏ FƏRQLƏNDİRİCİ ÜSTÜNLÜK\n" + answers.offer, "", "HƏDƏF AUDİTORİYA\n" + answers.audience, "", "BİZNES MƏQSƏDİ\n" + answers.goal, "", "TƏLƏB OLUNAN NƏTİCƏ\n" + answers.deliverable, "", "VİZUAL İSTİQAMƏT VƏ ÜNSİYYƏT TONU\n" + answers.tone, "", "MƏCBURİ TƏLƏBLƏR\n" + answers.requirements, "", "QAÇINILMALI MƏQAMLAR\n" + answers.avoid, "", "Nəticə konkret, brendə uyğun, tətbiq edilə bilən və aydın CTA ilə təqdim olunsun. Fərziyyələri ayrıca qeyd edin."].join("\n").slice(0, 2000);
  }
  function finish() {
    progress.style.width = "100%"; const brief = buildBrief(); message("agent", "Brifiniz hazırdır:\n\n" + brief); controls.hidden = true; actions.hidden = false; actions.innerHTML = "";
    const place = node("button", "brief-bot-action", "Brifə yerləşdir"), copy = node("button", "brief-bot-action secondary", "Kopyala"), restart = node("button", "brief-bot-action secondary", "Yenidən başla");
    place.onclick = function () { localStorage.setItem("agency_assisted_brief", brief); window.location.href = "/#briefRoom"; };
    copy.onclick = async function () { await navigator.clipboard.writeText(brief); copy.textContent = "Kopyalandı ✓"; };
    restart.onclick = reset; actions.append(place, copy, restart);
  }
  function submit() { const value = input.value.trim(); if (value.length < 2) { input.focus(); return; } answers[questions[step].key] = value; message("user", value); input.value = ""; step += 1; if (step >= questions.length) finish(); else ask(); }
  function reset() { step = 0; answers = {}; log.innerHTML = ""; actions.hidden = true; controls.hidden = false; ask(); }
  fab.onclick = function () { panel.hidden = !panel.hidden; if (!panel.hidden && !log.children.length) ask(); };
  panel.querySelector(".brief-bot-close").onclick = function () { panel.hidden = true; };
  panel.querySelector(".brief-bot-send").onclick = submit;
  input.addEventListener("keydown", function (event) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } });
})();
