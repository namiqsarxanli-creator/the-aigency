(function () {
  "use strict";
  // Yalniz platform owner-e (bax app/voice_demo_api.py `/voice-demo/status`) gorunur -
  // ISTENILEN NOMRE yox, hemise `.env`-deki DEMO_CALL_PHONE_NUMBER-e zeng edir.
  fetch("/voice-demo/status").then(function (r) { return r.json(); }).then(function (state) {
    if (!state.visible) return;
    var fab = document.createElement("button");
    fab.type = "button";
    fab.className = "call-fab";
    fab.setAttribute("aria-label", "Mənə zəng et (canlı demo)");
    if (!state.ready) fab.classList.add("call-fab-disabled");
    var icon = document.createElement("i"); icon.textContent = "☎";
    var label = document.createElement("span"); label.textContent = "Zəng et";
    fab.append(icon, label);
    document.body.appendChild(fab);

    fab.onclick = function () {
      if (fab.disabled) return;
      fab.disabled = true;
      label.textContent = "Zəng gedir…";
      fetch("/voice-demo/call", { method: "POST" })
        .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
        .then(function (res) {
          label.textContent = res.ok ? "Zəng edildi ✓" : (res.body.detail || "Xəta");
        })
        .catch(function () { label.textContent = "Server cavab vermir"; })
        .finally(function () {
          setTimeout(function () { fab.disabled = false; label.textContent = "Zəng et"; }, 4000);
        });
    };
  }).catch(function () { /* status alinmadi - isare sadece gorunmur */ });
})();
