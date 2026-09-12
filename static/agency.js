(function () {
  // Brendə uyğun confirm/alert — native window.confirm/alert saytın dizaynına yaraşmır
  // (OS-in öz boz qutusu kimi görünür). `type`: "confirm" | "success" | "error".
  function agencyModal(type, title, html, { okLabel = "Bağla", cancelLabel = "Ləğv et" } = {}) {
    return new Promise((resolve) => {
      const backdrop = document.createElement("div");
      backdrop.className = "agency-modal-backdrop";
      const icon = type === "error" ? "✕" : type === "success" ? "✓" : "📸";
      const modalClass = type === "error" ? "is-error" : type === "success" ? "is-success" : "";
      backdrop.innerHTML = `
        <div class="agency-modal ${modalClass}" role="dialog" aria-modal="true">
          <div class="agency-modal-icon">${icon}</div>
          <h3>${title}</h3>
          <p>${html}</p>
          <div class="agency-modal-actions">
            ${type === "confirm" ? `<button type="button" data-act="cancel">${cancelLabel}</button>` : ""}
            <button type="button" class="primary" data-act="ok">${type === "confirm" ? "Davam et" : okLabel}</button>
          </div>
        </div>`;
      document.body.appendChild(backdrop);
      requestAnimationFrame(() => backdrop.classList.add("is-open"));

      function close(result) {
        backdrop.classList.remove("is-open");
        setTimeout(() => backdrop.remove(), 250);
        resolve(result);
      }
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) close(false);
        const act = e.target.closest("[data-act]");
        if (act) close(act.dataset.act === "ok");
      });
    });
  }
  const confirmModal = (title, html) => agencyModal("confirm", title, html);
  const successModal = (title, html) => agencyModal("success", title, html);
  const errorModal = (title, html) => agencyModal("error", title, html);

  const briefForm = document.getElementById("briefForm");
  const briefInput = document.getElementById("briefInput");
  const briefSubmit = document.getElementById("briefSubmit");
  const projectSelect = document.getElementById("projectSelect");
  const feedBody = document.getElementById("feedBody");
  const board = document.getElementById("taskBoard");
  const liveDot = document.getElementById("liveDot");
  const deliverablePanel = document.getElementById("deliverablePanel");
  const deliverableFrameWrap = document.getElementById("deliverableFrameWrap");
  const deliverableFrame = document.getElementById("deliverableFrame");
  const socialPostPreview = document.getElementById("socialPostPreview");
  const socialPostImage = document.getElementById("socialPostImage");
  const socialPostCaption = document.getElementById("socialPostCaption");
  const deliverableStatus = document.getElementById("deliverableStatus");
  const approveBtn = document.getElementById("approveBtn");
  const rejectBtn = document.getElementById("rejectBtn");
  const instagramBtn = document.getElementById("instagramBtn");
  const exportReportBtn = document.getElementById("exportReportBtn");
  const exportZipBtn = document.getElementById("exportZipBtn");

  // Brif köməkçisinin başqa səhifədən hazırladığı promptu otağa təhlükəsiz köçür.
  if (briefInput) {
    const assistedBrief = localStorage.getItem("agency_assisted_brief");
    if (assistedBrief) {
      briefInput.value = assistedBrief.slice(0, 2000);
      localStorage.removeItem("agency_assisted_brief");
      briefInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  let currentProjectId = null;
  let feedSeen = new Set();

  const STATUS_LABELS = {
    BRIEF: "Plan hazırlanır…",
    IN_PROGRESS: "Komanda işləyir…",
    AWAITING_APPROVAL: "Təsdiqinizi gözləyir",
    DELIVERED: "Təhvil verildi ✅",
    REJECTED: "Rədd edildi ❌",
  };

  function roleLabel(role) {
    const map = {
      ceo: "CEO", strategist: "Strateq", copywriter: "Kopirayter",
      designer: "Dizayner", developer: "Developer",
      sales_strategist: "Satış Strateqi", outreach_writer: "Satış Kopirayteri",
      marketing: "Marketinq", analytics: "Analitika", legal: "Hüquq/Uyğunluq", finance: "Maliyyə",
      critic: "QA", human: "Siz",
    };
    return map[role] || role;
  }

  function highlightAgent(role) {
    document.querySelectorAll(".agent-card").forEach((el) => el.classList.remove("active"));
    const el = document.querySelector(`.agent-card[data-role="${role}"]`);
    if (el) {
      el.classList.add("active");
      setTimeout(() => el.classList.remove("active"), 4000);
    }
  }

  function appendFeedItem(ev, key) {
    if (key && feedSeen.has(key)) return;
    if (key) feedSeen.add(key);
    if (feedBody.querySelector(".empty")) feedBody.innerHTML = "";
    const div = document.createElement("details");
    div.className = `feed-item kind-${ev.kind || "chat"}`;
    const to = ev.to_role ? ` → ${roleLabel(ev.to_role)}` : " → komanda";
    const rawContent = ev.content || "";
    const preview = rawContent.replace(/[#*\n]+/g, " ").trim().slice(0, 118);
    div.innerHTML =
      `<summary>` +
        `<span class="feed-avatar">${roleLabel(ev.from_role).slice(0, 2).toUpperCase()}</span>` +
        `<span class="feed-summary"><span class="feed-head"><b>${roleLabel(ev.from_role)}${to}</b><em>${ev.kind || "event"}</em></span>` +
        `<span class="feed-preview">${escapeHtml(preview)}${rawContent.length > 118 ? "…" : ""}</span></span>` +
        `<i class="feed-toggle">＋</i>` +
      `</summary>` +
      `<div class="feed-content">${escapeHtml(rawContent)}</div>`;
    // Avtomatik aşağı sürüşmə YALNIZ istifadəçi onsuz da ən aşağıdadırsa. Əks halda
    // yuxarıdakı mesajı oxuyan adamı hər yeni hadisə aşağı dartırdı.
    const atBottom = feedBody.scrollHeight - feedBody.scrollTop - feedBody.clientHeight < 60;
    feedBody.appendChild(div);
    if (atBottom) feedBody.scrollTop = feedBody.scrollHeight;
    highlightAgent(ev.from_role);
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML.replace(/\n/g, "<br>");
  }

  function renderBoard(tasks) {
    board.querySelectorAll(".board-items").forEach((col) => (col.innerHTML = ""));
    document.querySelectorAll(".agent-card").forEach((card) => {
      card.classList.remove("task-done", "task-doing", "task-review");
    });
    (tasks || []).forEach((t) => {
      const col = board.querySelector(`.board-col[data-status="${t.status}"] .board-items`);
      if (!col) return;
      const card = document.createElement("div");
      card.className = "task-card";
      card.innerHTML = `<span class="task-role">${roleLabel(t.role)}</span>${escapeHtml(t.title)}`;
      col.appendChild(card);
      const agent = document.querySelector(`.agent-card[data-role="${t.role}"]`);
      if (agent) {
        if (t.status === "DONE") agent.classList.add("task-done");
        if (t.status === "DOING") agent.classList.add("task-doing");
        if (t.status === "REVIEW") agent.classList.add("task-review");
      }
    });
    board.querySelectorAll(".board-col").forEach((column) => {
      const count = column.querySelectorAll(".task-card").length;
      column.dataset.count = String(count);
    });
  }

  const DEPT_META = {
    strategist: { icon: "🎯", label: "Strategiya" },
    copywriter: { icon: "✍️", label: "Mətn (kopirayter)" },
    developer: { icon: "💻", label: "Developer (HTML)" },
    sales_strategist: { icon: "📈", label: "Satış strategiyası" },
    outreach_writer: { icon: "📧", label: "Satış mətnləri" },
    marketing: { icon: "📣", label: "Marketinq departamenti" },
    analytics: { icon: "🔢", label: "Analitika departamenti" },
    legal: { icon: "⚖️", label: "Hüquq / Uyğunluq departamenti" },
    finance: { icon: "💰", label: "Maliyyə departamenti" },
  };
  // Yenidən yazdırmaq yalnız iş bitəndən sonra mənalıdır (backend də eyni qaydanı tətbiq edir).
  const REGENERABLE = ["AWAITING_APPROVAL", "DELIVERED", "REJECTED"];

  function buildDeptReport(project, task) {
    const meta = DEPT_META[task.role];
    const det = document.createElement("details");
    det.className = "dept-report";
    const revBadge = task.revision_count
      ? `<span class="dept-rev">v${task.revision_count + 1}</span>`
      : "";
    det.innerHTML =
      `<summary>${meta.icon} ${meta.label}${revBadge}</summary>` +
      `<pre class="dept-report-body"></pre>` +
      `<div class="dept-actions">` +
        `<input class="dept-instruction" type="text" maxlength="1000" ` +
          `placeholder="Nəyi dəyişmək istəyirsən? (istəyə bağlı) — məs: daha qısa yaz, qiymətləri manatla göstər">` +
        `<button class="btn btn-ghost dept-regen" type="button">🔄 Yenidən yaz</button>` +
        (task.revision_count
          ? `<button class="btn btn-ghost dept-history" type="button">🕘 Köhnə variantlar</button>`
          : "") +
      `</div>` +
      `<div class="dept-versions" hidden></div>`;
    det.querySelector(".dept-report-body").textContent = task.output;

    const regenBtn = det.querySelector(".dept-regen");
    const instructionInput = det.querySelector(".dept-instruction");
    if (!REGENERABLE.includes(project.status)) {
      regenBtn.disabled = true;
      regenBtn.title = "Layihə hələ işləyir — bitməsini gözləyin.";
    }
    regenBtn.addEventListener("click", async () => {
      regenBtn.disabled = true;
      regenBtn.textContent = "⏳ Yazılır…";
      try {
        const res = await fetch(`/agency/${project.id}/task/${task.id}/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ instruction: instructionInput.value.trim() || null }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Yenidən yazmaq alınmadı.");
          return;
        }
        await loadProject(project.id);
      } catch (e) {
        alert("Şəbəkə xətası — yenidən cəhd edin.");
      } finally {
        regenBtn.disabled = false;
        regenBtn.textContent = "🔄 Yenidən yaz";
      }
    });

    const historyBtn = det.querySelector(".dept-history");
    if (historyBtn) {
      const box = det.querySelector(".dept-versions");
      historyBtn.addEventListener("click", async () => {
        if (!box.hidden) {
          box.hidden = true;
          return;
        }
        box.hidden = false;
        box.textContent = "Yüklənir…";
        try {
          const res = await fetch(`/agency/${project.id}/task/${task.id}/versions`);
          const data = await res.json();
          box.innerHTML = "";
          (data.versions || []).forEach((v) => {
            const item = document.createElement("details");
            item.className = "dept-version";
            item.innerHTML = `<summary>v${v.version_no} — köhnə variant</summary><pre></pre>`;
            item.querySelector("pre").textContent = v.output || "(boş)";
            box.appendChild(item);
          });
          if (!box.children.length) box.textContent = "Arxiv boşdur.";
        } catch (e) {
          box.textContent = "Versiyalar yüklənmədi.";
        }
      });
    }
    return det;
  }

  function renderDeliverable(project) {
    if (!["AWAITING_APPROVAL", "DELIVERED", "REJECTED"].includes(project.status) || !project.deliverable_html) {
      deliverablePanel.hidden = true;
      return;
    }
    deliverablePanel.hidden = false;
    deliverableStatus.textContent = STATUS_LABELS[project.status] || project.status;

    if (project.output_type === "social_post") {
      deliverableFrameWrap.hidden = true;
      socialPostPreview.hidden = false;
      socialPostCaption.textContent = project.deliverable_html || "";
      if (project.deliverable_image_url) {
        socialPostImage.src = project.deliverable_image_url;
        socialPostImage.style.display = "";
      } else {
        socialPostImage.style.display = "none";
      }
    } else {
      socialPostPreview.hidden = true;
      deliverableFrameWrap.hidden = false;
      deliverableFrame.srcdoc = project.deliverable_html;
    }

    // Satış departamentinin materialları (varsa)
    const salesKit = document.getElementById("salesKit");
    const salesKitBody = document.getElementById("salesKitBody");
    if (salesKit && salesKitBody) {
      if (project.sales_kit) {
        salesKit.hidden = false;
        salesKitBody.textContent = project.sales_kit;
      } else {
        salesKit.hidden = true;
      }
    }

    // Departament hesabatları — hər birini AYRICA yenidən yazdırmaq olar (bütün layihəni
    // təkrar işlətmədən). Köhnə variant arxivlənir, ona görə bu əməl geri alına biləndir.
    const deptReports = document.getElementById("deptReports");
    if (deptReports) {
      deptReports.innerHTML = "";
      (project.tasks || [])
        .filter((t) => DEPT_META[t.role] && (t.output || "").trim())
        .forEach((t) => {
          deptReports.appendChild(buildDeptReport(project, t));
        });
    }

    const locked = project.status !== "AWAITING_APPROVAL";
    approveBtn.disabled = locked;
    rejectBtn.disabled = locked;

    // Təhvil paketi — iş bitəndən sonra müştəriyə vermək üçün.
    if (exportReportBtn && exportZipBtn) {
      const canExport = REGENERABLE.includes(project.status);
      exportReportBtn.hidden = !canExport;
      exportZipBtn.hidden = !canExport;
      exportReportBtn.href = `/agency/${project.id}/export/report`;
      exportZipBtn.href = `/agency/${project.id}/export/zip`;
    }

    // Instagram: paylaşım düyməsi YALNIZ hesab həqiqətən qoşulubsa göstərilir.
    // Əks halda düymə mənasızdır — müştərinin Instagram-ı bağlı deyil, basanda heç nə ola
    // bilməz. Onun yerinə paketi təklif edirik.
    const igUpsell = document.getElementById("instagramUpsell");
    if (instagramBtn) {
      const isSocial =
        project.output_type === "social_post" &&
        ["AWAITING_APPROVAL", "DELIVERED"].includes(project.status);
      const connected = !!project.instagram_available;

      instagramBtn.hidden = !(isSocial && connected);
      if (project.instagram_published) {
        instagramBtn.disabled = true;
        instagramBtn.textContent = "📸 Instagram-da paylaşıldı ✓";
      } else {
        instagramBtn.disabled = false;
        instagramBtn.textContent = "📸 Instagram-da paylaş";
      }
      if (igUpsell) igUpsell.hidden = !(isSocial && !connected);
    }
  }

  async function loadProjects() {
    try {
      const res = await fetch("/agency/projects");
      const data = await res.json();
      projectSelect.innerHTML = '<option value="">— seçin —</option>' +
        data.map((p) => `<option value="${p.id}">#${p.id} — ${p.brief.slice(0, 50)}</option>`).join("");
      if (currentProjectId) projectSelect.value = String(currentProjectId);
    } catch (err) {
      /* siyahı yüklənmədi, davam et */
    }
  }

  // Layihə hələ işləyirsə lövhəni qısa intervalla yeniləyirik.
  // NİYƏ LAZIMDIR: agent DOING vəziyyətinə keçəndə server HEÇ BİR hadisə göndərmir —
  // hadisə yalnız iş BİTƏNDƏN sonra yayımlanır. Ona görə tapşırıqlar TODO-dan birbaşa
  // DONE-a "tullanırdı" və istifadəçi nə DOING, nə REVIEW mərhələsini görürdü.
  let pollTimer = null;
  const ACTIVE_POLL_MS = 1500;

  function scheduleActivePoll(project) {
    clearTimeout(pollTimer);
    if (!project || REGENERABLE.includes(project.status)) return;  // iş bitib, yenilməyə ehtiyac yoxdur
    pollTimer = setTimeout(() => {
      if (currentProjectId) loadProject(currentProjectId);
    }, ACTIVE_POLL_MS);
  }

  async function loadProject(id, options) {
    // `reset` YALNIZ başqa layihəyə keçəndə true olur. Əvvəl hər yenilənmədə lent tamamilə
    // silinib yenidən qurulurdu — nəticədə istifadəçi bir mesajı oxumaq üçün açanda növbəti
    // agent hadisəsi onu dərhal bağlayırdı və söhbəti izləmək mümkün olmurdu.
    const switching = (options && options.reset) || id !== currentProjectId;
    currentProjectId = id;
    projectSelect.value = String(id);
    try {
      const res = await fetch(`/agency/${id}`);
      if (!res.ok) return;
      const project = await res.json();
      if (switching) {
        feedSeen = new Set();
        feedBody.innerHTML = "";
      }
      // `feedSeen` təkrarların qarşısını alır, ona görə lent yalnız ARTIR — açıq mesajlar
      // və istifadəçinin sürüşdürmə mövqeyi qorunur.
      (project.messages || []).forEach((m) => appendFeedItem(m, `m${m.id}`));
      renderBoard(project.tasks);
      renderDeliverable(project);
      scheduleActivePoll(project);
    } catch (err) {
      /* sakitcə keç */
    }
  }

  async function runProject(id) {
    briefSubmit.disabled = true;
    // ƏVVƏLCƏ lövhəni yüklə, SONRA işə başla. `/run` sorğusu bütün pipeline bitənə qədər
    // (30-60 saniyə) cavab vermir — əvvəl `loadProject` yalnız `finally` blokunda çağırılırdı,
    // yəni lövhə İLK DƏFƏ iş tam bitəndən sonra çəkilirdi və istifadəçi tapşırıqları birbaşa
    // DONE-da görürdü (canlı tapıntı: TODO/DOING/REVIEW heç vaxt görünmürdü).
    // İki şeyi işə salır: (1) `currentProjectId` təyin olunur — WebSocket hadisələri artıq
    // "başqa layihə" deyə atılmır və hər addımda lövhəni yeniləyir; (2) `scheduleActivePoll`
    // zənciri başlayır — server hadisə göndərməyən DOING anlarında da lövhə canlı qalır.
    await loadProject(id);
    try {
      await fetch(`/agency/${id}/run`, { method: "POST" });
    } catch (err) {
      /* WS artıq addımları göstərmiş ola bilər */
    } finally {
      briefSubmit.disabled = false;
      briefSubmit.innerHTML = "<span>Şirkəti işə sal</span><b>↗</b>";
      loadProject(id);
      loadProjects();
    }
  }

  briefForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const brief = briefInput.value.trim();
    if (!brief) return;
    briefSubmit.disabled = true;
    briefSubmit.innerHTML = "<span>Komanda işə düşür…</span><b>···</b>";
    try {
      const res = await fetch("/agency/brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief }),
      });
      const project = await res.json();
      briefInput.value = "";
      await loadProjects();
      runProject(project.id);
    } catch (err) {
      briefSubmit.disabled = false;
      briefSubmit.innerHTML = "<span>Şirkəti işə sal</span><b>↗</b>";
    }
  });

  projectSelect.addEventListener("change", () => {
    // reset:true — başqa layihəyə keçirik, köhnə söhbət lenti tam silinməlidir.
    if (projectSelect.value) loadProject(Number(projectSelect.value), { reset: true });
  });

  approveBtn.addEventListener("click", async () => {
    if (!currentProjectId) return;
    await fetch(`/agency/${currentProjectId}/approve`, { method: "POST" });
    loadProject(currentProjectId);
  });

  rejectBtn.addEventListener("click", async () => {
    if (!currentProjectId) return;
    const reason = window.prompt(
      "Rədd səbəbini yazın (ixtiyaridir) — yazsanız, komanda bunu nəzərə alıb avtomatik yeni cəhdə başlayacaq:",
      ""
    );
    if (reason === null) return; // ləğv edildi
    await fetch(`/agency/${currentProjectId}/reject`, {
      method: "POST",
      headers: reason.trim() ? { "Content-Type": "application/json" } : undefined,
      body: reason.trim() ? JSON.stringify({ reason: reason.trim() }) : undefined,
    });
    loadProject(currentProjectId);
  });

  if (instagramBtn) {
    instagramBtn.addEventListener("click", async () => {
      if (!currentProjectId) return;
      const ok = await confirmModal(
        "Instagram-da paylaş",
        "Bu post birbaşa Instagram hesabınızda dərc olunacaq. Bu addım geri alınmır. Davam edilsin?"
      );
      if (!ok) return;
      instagramBtn.disabled = true;
      instagramBtn.textContent = "📸 Paylaşılır…";
      try {
        const res = await fetch(`/agency/${currentProjectId}/publish-instagram`, { method: "POST" });
        const data = await res.json();
        if (data.ok) {
          await successModal(
            "Paylaşıldı",
            data.permalink
              ? `Post Instagram-da dərc olundu. <a href="${data.permalink}" target="_blank" rel="noopener">Posta bax →</a>`
              : "Post Instagram-da dərc olundu."
          );
        } else {
          await errorModal("Paylaşıla bilmədi", data.detail || "Naməlum xəta baş verdi.");
        }
      } catch (e) {
        await errorModal("Paylaşıla bilmədi", e.message || "Serverə qoşulmaq mümkün olmadı.");
      }
      loadProject(currentProjectId);
    });
  }

  let retryDelay = 2000;
  function connectWs() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/live`);
    ws.onopen = () => {
      liveDot.classList.add("on");
      retryDelay = 2000;
    };
    ws.onclose = () => {
      liveDot.classList.remove("on");
      setTimeout(connectWs, retryDelay);
      retryDelay = Math.min(retryDelay * 1.5, 20000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type !== "agent_event") return;
        if (currentProjectId && data.project_id !== currentProjectId) return;
        if (currentProjectId) {
          // `loadProject` mesajı ID-si ilə əlavə edir (təkrarsız). Burada ayrıca
          // `appendFeedItem` çağırsaq, eyni mesaj iki dəfə görünərdi — biri açarsız,
          // biri `m{id}` açarı ilə.
          loadProject(currentProjectId);
        } else {
          appendFeedItem(data);   // layihə seçilməyib — ümumi canlı lent kimi göstər
        }
      } catch (err) {
        /* pozuq frame, keç */
      }
    };
  }

  connectWs();
  loadProjects();

  // Kino hissi yaradan yüngül parallax və scroll reveal.
  const fresco = document.querySelector(".fresco-stage");
  const revealBlocks = document.querySelectorAll(".reveal");
  let scrollTicking = false;

  function updateFresco() {
    if (fresco && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const progress = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 1);
      document.querySelector(".hero")?.style.setProperty("--enter", progress.toFixed(3));
    }
    scrollTicking = false;
  }

  window.addEventListener("scroll", () => {
    if (!scrollTicking) {
      requestAnimationFrame(updateFresco);
      scrollTicking = true;
    }
  }, { passive: true });

  // =========================================================================
  // GLOBAL GALLERY DRAWER MODAL
  // =========================================================================
  const menuToggleBtn = document.getElementById("menuToggleBtn");
  const galleryMenuDrawer = document.getElementById("galleryMenuDrawer");
  const drawerCloseBtn = document.getElementById("drawerCloseBtn");
  const drawerBackdrop = document.getElementById("drawerBackdrop");

  function openDrawer() {
    if (galleryMenuDrawer) {
      galleryMenuDrawer.classList.add("is-open");
      galleryMenuDrawer.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    }
  }

  function closeDrawer() {
    if (galleryMenuDrawer) {
      galleryMenuDrawer.classList.remove("is-open");
      galleryMenuDrawer.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }
  }

  if (menuToggleBtn) menuToggleBtn.addEventListener("click", openDrawer);
  if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", closeDrawer);
  if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeDrawer);

  document.querySelectorAll(".drawer-card").forEach((link) => {
    link.addEventListener("click", closeDrawer);
  });

  // =========================================================================
  // 3D CONTINUOUS CAMERA STREAM & GALLERY ZOOM ENGINE
  // =========================================================================
  const cameraRig = document.getElementById("cameraRig");
  const sceneAthensCorridor = document.getElementById("sceneAthensCorridor");
  const sceneAthensPainting = document.getElementById("sceneAthensPainting");
  const sceneSocratesRoom = document.getElementById("sceneSocratesRoom");
  const sceneSocratesPainting = document.getElementById("sceneSocratesPainting");
  const visitorSilhouettes = document.getElementById("visitorSilhouettes");

  const cardAthens = document.getElementById("cardAthens");
  const cardSocrates = document.getElementById("cardSocrates");
  const streamStatYear = document.getElementById("streamStatYear");
  const streamStatFigures = document.getElementById("streamStatFigures");
  const streamStatWidth = document.getElementById("streamStatWidth");

  const btnEnterGallery = document.getElementById("btnEnterGallery");
  const btnSocratesGallery = document.getElementById("btnSocratesGallery");

  let cameraProgress = 0.0;
  let targetProgress = 0.0;
  let currentRoomId = "studio";

  // Gimbal state for 3D mouse look-around
  const gimbal = {
    targetX: 0,
    targetY: 0,
    currX: 0,
    currY: 0,
    ambient: 0,
  };

  // Main Camera Render Loop (60/120fps Smooth Inertia Stream)
  function renderCameraStream() {
    // Ambient camera drift
    gimbal.ambient += 0.016;
    const ambX = Math.sin(gimbal.ambient) * 0.03;
    const ambY = Math.cos(gimbal.ambient * 0.7) * 0.03;

    // Smooth Lerp
    cameraProgress += (targetProgress - cameraProgress) * 0.08;
    gimbal.currX += (gimbal.targetX + ambX - gimbal.currX) * 0.075;
    gimbal.currY += (gimbal.targetY + ambY - gimbal.currY) * 0.075;

    // Apply continuous 3D camera timeline
    const p = Math.max(0, Math.min(1.0, cameraProgress));

    // Phase 1 (0.0 to 0.5): Zoom into Athens Corridor & Painting
    if (p <= 0.5) {
      const localP = p / 0.5; // 0 to 1

      // Scene 1 Corridor transforms
      if (sceneAthensCorridor) {
        sceneAthensCorridor.classList.add("active");
        sceneAthensCorridor.style.opacity = Math.max(0, 1 - localP * 1.6).toFixed(3);
        sceneAthensCorridor.style.transform = `
          translate3d(${gimbal.currX * -25}px, ${gimbal.currY * -18}px, ${localP * 350}px)
          scale(${1 + localP * 1.8})
          rotateX(${gimbal.currY * -2.5}deg)
          rotateY(${gimbal.currX * 3.5}deg)
        `;
      }

      // Visitors sink down as camera flies past
      if (visitorSilhouettes) {
        visitorSilhouettes.style.transform = `translateX(-50%) translateY(${localP * 280}px) scale(${1 + localP * 0.6})`;
        visitorSilhouettes.style.opacity = Math.max(0, 1 - localP * 2.2).toFixed(3);
      }

      // Scene 2 Painting emerges full bleed
      if (sceneAthensPainting) {
        sceneAthensPainting.classList.toggle("active", localP > 0.08);
        sceneAthensPainting.style.opacity = Math.min(1, localP * 2.2).toFixed(3);
        sceneAthensPainting.style.transform = `
          translate3d(${gimbal.currX * -35}px, ${gimbal.currY * -25}px, ${(1 - localP) * -200}px)
          scale(${0.9 + localP * 0.15})
          rotateX(${gimbal.currY * -1.8}deg)
          rotateY(${gimbal.currX * 2.5}deg)
        `;
      }

      if (sceneSocratesRoom) sceneSocratesRoom.classList.remove("active");
      if (sceneSocratesPainting) sceneSocratesPainting.classList.remove("active");

      // UI state Athens
      if (cardAthens) cardAthens.classList.add("active");
      if (cardSocrates) cardSocrates.classList.remove("active");
      if (streamStatYear) streamStatYear.textContent = "1511";
      if (streamStatFigures) streamStatFigures.textContent = "21";
      if (streamStatWidth) streamStatWidth.textContent = "770 cm";
    }
    // Phase 2 (0.5 to 1.0): Socrates Gallery
    else {
      const localP = (p - 0.5) / 0.5; // 0 to 1

      if (sceneAthensCorridor) sceneAthensCorridor.classList.remove("active");
      if (sceneAthensPainting) {
        sceneAthensPainting.style.opacity = Math.max(0, 1 - localP * 3).toFixed(3);
      }

      // Scene 3 Socrates Room emerges
      if (sceneSocratesRoom) {
        sceneSocratesRoom.classList.add("active");
        sceneSocratesRoom.style.opacity = Math.max(0, 1 - localP * 1.5).toFixed(3);
        sceneSocratesRoom.style.transform = `
          translate3d(${gimbal.currX * -25}px, ${gimbal.currY * -18}px, ${localP * 300}px)
          scale(${1 + localP * 1.6})
          rotateX(${gimbal.currY * -2.5}deg)
          rotateY(${gimbal.currX * 3.5}deg)
        `;
      }

      // Scene 4 Socrates Painting
      if (sceneSocratesPainting) {
        sceneSocratesPainting.classList.toggle("active", localP > 0.15);
        sceneSocratesPainting.style.opacity = Math.min(1, localP * 2.2).toFixed(3);
        sceneSocratesPainting.style.transform = `
          translate3d(${gimbal.currX * -35}px, ${gimbal.currY * -25}px, 0px)
          scale(${0.9 + localP * 0.15})
          rotateX(${gimbal.currY * -1.8}deg)
          rotateY(${gimbal.currX * 2.5}deg)
        `;
      }

      // UI state Socrates
      if (cardAthens) cardAthens.classList.remove("active");
      if (cardSocrates) cardSocrates.classList.add("active");
      if (streamStatYear) streamStatYear.textContent = "1787";
      if (streamStatFigures) streamStatFigures.textContent = "12";
      if (streamStatWidth) streamStatWidth.textContent = "196 cm";
    }

    // Sub-rooms parallax updates
    const currentRoom = document.querySelector(".room.is-current");
    if (currentRoom) {
      currentRoom.style.setProperty("--rx", gimbal.currX.toFixed(3));
      currentRoom.style.setProperty("--ry", gimbal.currY.toFixed(3));
    }

    requestAnimationFrame(renderCameraStream);
  }
  requestAnimationFrame(renderCameraStream);

  // Mouse Move Gimbal
  window.addEventListener("pointermove", (e) => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    gimbal.targetX = Math.max(-1, Math.min(1, (e.clientX / w - 0.5) * 2));
    gimbal.targetY = Math.max(-1, Math.min(1, (e.clientY / h - 0.5) * 2));
  }, { passive: true });

  // Scroll wheel continuous camera stream scrub
  window.addEventListener("wheel", (e) => {
    if (e.target.closest("#feedBody, #taskBoard, textarea, select, .drawer-panel, .dept-report-body")) return;

    if (window.scrollY <= 15) {
      if (e.deltaY > 0) {
        if (targetProgress < 0.96) {
          targetProgress = Math.min(1.0, targetProgress + e.deltaY * 0.0018);
        } else {
          // Beyond end of studio gallery -> smoothly scroll to Brief Room
          const brief = document.getElementById("briefRoom");
          if (brief) brief.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } else {
        targetProgress = Math.max(0, targetProgress + e.deltaY * 0.0018);
      }
    }
  }, { passive: true });

  // "Enter the Gallery" button smooth camera flight
  if (btnEnterGallery) {
    btnEnterGallery.addEventListener("click", (e) => {
      e.preventDefault();
      targetProgress = targetProgress < 0.4 ? 0.48 : 0.88;
    });
  }
  if (btnSocratesGallery) {
    btnSocratesGallery.addEventListener("click", (e) => {
      e.preventDefault();
      targetProgress = 0.95;
    });
  }

  // Smooth Navigation to Room
  function navigateToRoom(targetRoomId) {
    const targetEl = document.getElementById(targetRoomId);
    if (!targetEl) return;
    currentRoomId = targetRoomId;
    closeDrawer();
    targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", "#" + targetRoomId);
  }

  window.openDrawer = openDrawer;
  window.closeDrawer = closeDrawer;
  window.droneFlyTo = navigateToRoom;

  // Mobile Touch Swipe Scrub
  let touchStartY = 0;
  window.addEventListener("touchstart", (e) => {
    touchStartY = e.touches[0].clientY;
  }, { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (window.scrollY <= 15) {
      const dy = touchStartY - e.touches[0].clientY;
      touchStartY = e.touches[0].clientY;
      targetProgress = Math.max(0, Math.min(1.0, targetProgress + dy * 0.003));
    }
  }, { passive: true });

  // Room intersection tracking for sub-rooms
  if ("IntersectionObserver" in window) {
    const roomObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle("is-current", entry.isIntersecting);
        if (entry.isIntersecting) {
          const id = entry.target.id;
          if (id) currentRoomId = id;
        }
      });
    }, { threshold: 0.45 });

    document.querySelectorAll(".room, .palace-hero").forEach((el) => roomObserver.observe(el));
  }

  if ("IntersectionObserver" in window) {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealBlocks.forEach((block) => revealObserver.observe(block));
  } else {
    revealBlocks.forEach((block) => block.classList.add("is-visible"));
  }
})();
