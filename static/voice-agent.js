/* Səsli agent widget-i — hər səhifədə üzən "Zəng et" düyməsi.
 * Nitq tanıma: brauzerin öz Web Speech API-si (server audio görmür, pulsuzdur).
 * Səsləndirmə: brauzer varsa öz Azərbaycanca səsi, yoxsa server (Azure) fallback.
 */
(function () {
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;

  let sessionId = null;
  let history = [];
  let recognizer = null;
  let listening = false;
  let panelOpen = false;
  let serverTts = false;
  let browserVoice = null;

  function pickBrowserVoice() {
    const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    // Tam "az-AZ" nadirdir — "az" ilə başlayan hər hansı səsi qəbul edirik.
    browserVoice = voices.find((v) => /^az/i.test(v.lang)) || null;
    return browserVoice;
  }
  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = pickBrowserVoice;
    pickBrowserVoice();
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    });
    children.forEach((c) => c && node.appendChild(c));
    return node;
  }

  function build() {
    const fab = el("button", { class: "voice-fab", type: "button", "aria-label": "Zəng et", title: "Zəng et" }, el("span", { text: "📞" }));
    const panel = el("div", { class: "voice-panel", hidden: "" });
    panel.innerHTML =
      '<div class="voice-head"><span>📞 AI ilə danış</span><button class="voice-close" type="button" aria-label="Bağla">✕</button></div>' +
      '<div class="voice-log" id="voiceLog"></div>' +
      '<div class="voice-status" id="voiceStatus">Zəngi başlatmaq üçün mikrofon düyməsinə basın.</div>' +
      '<div class="voice-controls">' +
      '<button class="voice-mic" id="voiceMic" type="button" aria-label="Danış">🎤</button>' +
      '<input class="voice-text" id="voiceText" type="text" placeholder="Ya da buraya yazın…" maxlength="500">' +
      '<button class="voice-send" id="voiceSend" type="button">Göndər</button>' +
      "</div>";
    document.body.appendChild(fab);
    document.body.appendChild(panel);
    return { fab, panel };
  }

  function appendLog(role, text) {
    const log = document.getElementById("voiceLog");
    const bubble = el("div", { class: `voice-bubble voice-${role}` }, el("span", { text }));
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
  }

  function setStatus(text) {
    const status = document.getElementById("voiceStatus");
    if (status) status.textContent = text;
  }

  async function speak(text) {
    if (browserVoice && window.speechSynthesis) {
      const utter = new SpeechSynthesisUtterance(text);
      utter.voice = browserVoice;
      utter.lang = "az-AZ";
      window.speechSynthesis.speak(utter);
      return;
    }
    if (!serverTts) return; // nə brauzer səsi, nə server konfiqurasiyası — yalnız mətn qalır
    try {
      const res = await fetch("/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (res.status !== 200) return; // 204 = server TTS də yoxdur, mətnlə kifayətlənirik
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.play().catch(() => {});
    } catch (e) {
      /* səssizcə keç — mətn onsuz da göründü */
    }
  }

  async function sendTurn(text) {
    if (!text || !text.trim() || !sessionId) return;
    appendLog("user", text);
    history.push({ role: "user", text });
    setStatus("Cavab hazırlanır…");
    document.getElementById("voiceSend").disabled = true;
    try {
      const res = await fetch("/voice/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text, history }),
      });
      if (!res.ok) {
        setStatus("Bir xəta oldu. Bir daha cəhd edin.");
        return;
      }
      const data = await res.json();
      appendLog("agent", data.reply);
      history.push({ role: "agent", text: data.reply });
      serverTts = !!data.server_tts;
      speak(data.reply);
      if (data.action === "create_brief" && data.project_id) {
        setStatus("İstəyiniz qeyd olundu — komandamız işə başladı. Başqa sualınız var?");
      } else if (data.action === "handoff") {
        setStatus("Sizi həmkarımıza yönləndiririk.");
      } else if (data.action === "capture_lead") {
        setStatus("Məlumatınız qeyd olundu, tezliklə sizinlə əlaqə saxlanılacaq.");
      } else {
        setStatus("Dinləyirəm…");
      }
    } catch (e) {
      setStatus("Şəbəkə xətası — bir daha cəhd edin.");
    } finally {
      document.getElementById("voiceSend").disabled = false;
    }
  }

  function startListening() {
    if (!SpeechRecognitionImpl) {
      setStatus("Brauzeriniz səslə tanımanı dəstəkləmir — yazaraq davam edin.");
      return;
    }
    if (listening) {
      recognizer && recognizer.stop();
      return;
    }
    recognizer = new SpeechRecognitionImpl();
    recognizer.lang = "az-AZ";
    recognizer.interimResults = false;
    recognizer.maxAlternatives = 1;
    recognizer.onstart = () => {
      listening = true;
      document.getElementById("voiceMic").classList.add("active");
      setStatus("Dinləyirəm…");
    };
    recognizer.onresult = (event) => {
      const text = event.results[0][0].transcript;
      sendTurn(text);
    };
    // Brauzerlər hansı dilləri dəstəklədiyini ƏVVƏLCƏDƏN bildirmir — yalnız cəhd edəndə
    // məlum olur (bax MDN: SpeechRecognitionErrorEvent). Ona görə səbəbi DƏQİQ göstəririk,
    // "səs tanınmadı" kimi ümumi mesaj həllin harada olduğunu gizlədirdi.
    recognizer.onerror = (event) => {
      const messages = {
        "not-allowed": "Mikrofona icazə verilmədi. Brauzerin ünvan çubuğundakı 🔒 işarəsindən icazə verin.",
        "service-not-allowed": "Mikrofona icazə verilmədi. Brauzer ayarlarından icazə verin.",
        "language-not-supported": "Bu brauzer Azərbaycan dilində səs tanımanı dəstəkləmir — zəhmət olmasa yazın.",
        "network": "Şəbəkə problemi səbəbindən səs tanınmadı — yazaraq davam edin.",
        "no-speech": "Səs eşidilmədi. Bir daha mikrofon düyməsinə basıb danışın.",
        "audio-capture": "Mikrofon tapılmadı — cihazınızda mikrofon qoşulu olduğuna əmin olun.",
        "aborted": "Dinləmə dayandırıldı.",
      };
      setStatus(messages[event.error] || `Səs tanınmadı (${event.error}) — yazaraq davam edin.`);
      console.warn("[voice-agent] SpeechRecognition error:", event.error);
    };
    recognizer.onend = () => {
      listening = false;
      document.getElementById("voiceMic").classList.remove("active");
    };
    recognizer.start();
  }

  async function openPanel(panel) {
    panel.hidden = false;
    panelOpen = true;
    if (!sessionId) {
      setStatus("Qoşulur…");
      try {
        const res = await fetch("/voice/config");
        if (!res.ok) {
          setStatus("Səsli agent hazırda əlçatan deyil.");
          return;
        }
        const cfg = await res.json();
        sessionId = cfg.session_id;
        serverTts = !!cfg.server_tts;
        appendLog("agent", cfg.greeting);
        history.push({ role: "agent", text: cfg.greeting });
        setStatus("Zəngi başlatmaq üçün mikrofon düyməsinə basın.");
        speak(cfg.greeting);
      } catch (e) {
        setStatus("Qoşulma alınmadı — bir daha cəhd edin.");
      }
    }
  }

  function init() {
    const { fab, panel } = build();
    fab.addEventListener("click", () => {
      if (panelOpen) {
        panel.hidden = true;
        panelOpen = false;
      } else {
        openPanel(panel);
      }
    });
    panel.querySelector(".voice-close").addEventListener("click", () => {
      panel.hidden = true;
      panelOpen = false;
      if (listening) recognizer && recognizer.stop();
    });
    panel.querySelector("#voiceMic").addEventListener("click", startListening);
    panel.querySelector("#voiceSend").addEventListener("click", () => {
      const input = document.getElementById("voiceText");
      sendTurn(input.value);
      input.value = "";
    });
    panel.querySelector("#voiceText").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        panel.querySelector("#voiceSend").click();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
