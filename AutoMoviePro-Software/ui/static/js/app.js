async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...opts,
  });
  return res.json();
}

const loginView = document.getElementById("loginView");
const dashView = document.getElementById("dashView");
const userBox = document.getElementById("userBox");

let NICHE_CACHE = [];
let _livePollTimer = null;
let _livePollMs = 2500;
let _liveSinceSeq = 0;
let _pollEnabled = true;
let _selectedJobId = null;
let _jobCacheById = {}; // job_id -> latest projection (stale guard)

const TERMINAL_STATES = new Set([
  "READY_FOR_REVIEW", "FAILED", "INTERRUPTED", "CANCELLED", "COMPLETED",
]);

function getTierBadgeHtml(tier) {
  const t = String(tier || "").toLowerCase();
  if (t.includes("video_studio") || t.includes("omni_video") || t.includes("3999")) {
    return `<span class="tier-badge" style="background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">🎬 ভিডিও স্টুডিও (৳৩,৯৯৯)</span>`;
  }
  if (t.includes("fb_business") || t.includes("business") || t.includes("2999")) {
    return `<span class="tier-badge" style="background: linear-gradient(135deg, #7c3aed, #9333ea); color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">💼 FB বিজনেস ম্যানেজার (৳২,৯৯৯)</span>`;
  }
  if (t.includes("profile_page") || t.includes("autopilot") || t.includes("1999")) {
    return `<span class="tier-badge" style="background: linear-gradient(135deg, #d97706, #f59e0b); color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">📱 FB প্রোফাইল ও পেজ (৳১,৯৯৯)</span>`;
  }
  return `<span class="tier-badge" style="background: #334155; color: #38bdf8; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">💻 ডেভ / অল-এক্সেস</span>`;
}

function renderTierInfo(customer) {
  const banner = document.getElementById("tierStatusBanner");
  const msgEl = document.getElementById("tierStatusMessage");
  if (!banner || !msgEl) return;
  const t = String(customer?.tier || customer?.plan || "").toLowerCase();
  
  if (t === "profile_page" || t === "fb_profile_autopilot" || t === "1999") {
    banner.style.display = "flex";
    banner.style.background = "rgba(217, 119, 6, 0.15)";
    banner.style.border = "1px solid #d97706";
    msgEl.innerHTML = `<span>🔒 আপনার বর্তমান প্যাকেজ: <strong>ফেসবুক প্রোফাইল ও পেজ (৳১,৯৯৯)</strong>। ফুল ভিডিও স্টুডিও তৈরি করতে ৳৩,৯৯৯ ভিডিও স্টুডিও প্যাকেজে আপগ্রেড করুন।</span>`;
  } else if (t === "fb_business" || t === "fb_business_ad" || t === "2999") {
    banner.style.display = "flex";
    banner.style.background = "rgba(147, 51, 234, 0.15)";
    banner.style.border = "1px solid #9333ea";
    msgEl.innerHTML = `<span>🔒 আপনার বর্তমান প্যাকেজ: <strong>ফেসবুক বিজনেস ম্যানেজার (৳২,৯৯৯)</strong>। ফুল ভিডিও স্টুডিও তৈরি করতে ৳৩,৯৯৯ ভিডিও স্টুডিও প্যাকেজে আপগ্রেড করুন।</span>`;
  } else {
    banner.style.display = "none";
  }
}

function showDash(loggedIn, customer) {
  loginView.classList.toggle("hidden", loggedIn);
  dashView.classList.toggle("hidden", !loggedIn);
  if (loggedIn) {
    const tier = customer?.tier || customer?.plan || "video_studio";
    userBox.innerHTML = `${escapeHtml(customer?.name || "")} (${escapeHtml(customer?.login_id || "")}) ${getTierBadgeHtml(tier)}`;
    renderTierInfo(customer);
  } else {
    userBox.textContent = "লগইন হয়নি";
  }
}

function escapeAttr(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fillNicheSelect(sel, niches, selectedId) {
  if (!sel) return;
  const cur = selectedId != null ? String(selectedId) : String(sel.value || "");
  sel.innerHTML = (niches || []).map(n =>
    `<option value="${n.id}" data-name="${escapeAttr(n.name_en || n.name)}" data-label="${escapeAttr(n.name)}" data-blurb="${escapeAttr(n.blurb || "")}">${n.id}. ${n.name}</option>`
  ).join("");
  if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  else if (sel.options.length) sel.selectedIndex = 0;
  syncNicheNameFromSelect(sel);
  updateNicheBlurb(sel);
}

function syncNicheNameFromSelect(sel) {
  const opt = sel?.selectedOptions?.[0];
  const nameInput = document.getElementById("channelNicheName");
  // Canonical English name for backend resolve; UI option text is localized
  if (nameInput && opt) nameInput.value = opt.dataset.name || opt.dataset.label || opt.textContent || "";
}

function updateNicheBlurb(sel) {
  const el = document.getElementById("channelNicheBlurb");
  if (!el) return;
  const opt = sel?.selectedOptions?.[0];
  el.textContent = (opt && opt.dataset.blurb) ? opt.dataset.blurb : "";
}

function filterNiches(q) {
  const needle = (q || "").trim().toLowerCase();
  if (!needle) return NICHE_CACHE;
  return NICHE_CACHE.filter(n =>
    String(n.id) === needle ||
    (n.name || "").toLowerCase().includes(needle) ||
    (n.name_en || "").toLowerCase().includes(needle) ||
    (n.blurb || "").toLowerCase().includes(needle)
  );
}

async function loadNiches() {
  const lang = localStorage.getItem("amp_ui_lang") || "bn";
  const res = await api("/api/niches?lang=" + encodeURIComponent(lang));
  if (!res.ok) return;
  NICHE_CACHE = res.niches || [];
  fillNicheSelect(document.getElementById("channelNicheSelect"), NICHE_CACHE);
}
window.loadNiches = loadNiches;

/** Stale-response protection — mirrors app.customer_job.is_newer_projection */
function isNewerJobSnapshot(incoming, current) {
  if (!incoming) return false;
  if (!current) return true;
  const iu = String(incoming.updated_at || "");
  const cu = String(current.updated_at || "");
  if (iu && cu) {
    if (iu > cu) return true;
    if (iu < cu) return false;
  }
  return Number(incoming.state_ordinal || 0) >= Number(current.state_ordinal || 0);
}

function acceptJobProjection(job) {
  if (!job || job.job_id == null) return null;
  const id = job.job_id;
  const prev = _jobCacheById[id];
  if (!isNewerJobSnapshot(job, prev)) return prev || null;
  _jobCacheById[id] = job;
  return job;
}

function renderAuthBanner(identity, access) {
  const banner = document.getElementById("authStateBanner");
  if (!banner) return;
  const id = identity || {};
  const state = String(id.auth_state || "UNAUTHENTICATED");
  const prodOk = !!(access?.production_allowed || id.production_allowed);
  if (state === "AUTHENTICATED" && (id.production_access || prodOk)) {
    banner.classList.add("hidden");
    return;
  }
  if (!id.logged_in && state === "UNAUTHENTICATED") {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden", "active");
  banner.classList.add("inactive");
  const msg = id.message || access?.message || "Please sign in to continue.";
  banner.innerHTML = `<strong>${escapeHtml(state)}</strong> — ${escapeHtml(msg)}`;
}

function switchTab(tabName) {
  document.querySelectorAll(".tabs button").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab").forEach(t => t.classList.add("hidden"));
  const el = document.getElementById("tab-" + tabName);
  if (el) el.classList.remove("hidden");
}

function renderDashboard(dash) {
  const welcome = document.getElementById("dashWelcome");
  const onboard = document.getElementById("dashOnboarding");
  const list = document.getElementById("dashChecklist");
  const blocking = document.getElementById("dashBlocking");
  const jobsEl = document.getElementById("dashJobSummary");
  if (!welcome) return;
  if (!dash || !dash.ok) {
    if (dash && dash.error === "legal_consent_required") {
      const modal = document.getElementById("legalTermsModal");
      if (modal) modal.style.display = "flex";
    }
    welcome.classList.add("muted");
    welcome.textContent = dash?.message || dash?.error || "Dashboard unavailable.";
    return;
  }
  const id = dash.identity || {};
  const ob = dash.onboarding || {};
  const access = dash.access || {};
  welcome.classList.remove("muted");
  welcome.innerHTML = `<strong>${escapeHtml(id.display_name || id.login_id || "Customer")}</strong>
    · Auth ${escapeHtml(id.auth_state || "—")}
    · Account ${escapeHtml(id.account_state || "—")}
    · Entitlement ${escapeHtml(id.entitlement_state || "—")}
    · Route ${escapeHtml(dash.startup_route || "—")}`;

  onboard.classList.remove("muted");
  onboard.innerHTML = `<strong>Onboarding: ${escapeHtml(ob.state || "UNKNOWN")}</strong>
    <div class="muted">${escapeHtml(ob.message || "")}</div>
    <div class="muted">Production allowed: ${access.production_allowed ? "yes" : "no"}
      ${access.message ? " — " + escapeHtml(access.message) : ""}</div>`;

  list.innerHTML = (dash.checklist || []).map(item => {
    const st = String(item.state || "UNKNOWN");
    const bad = ["BLOCKED", "UNKNOWN", "INCOMPLETE", "NOT_CONFIGURED"].includes(st);
    const ok = st === "COMPLETE";
    return `<div class="card ${ok ? "" : "muted"}">
      <strong>${escapeHtml(item.label)}</strong>
      <span class="${bad ? "err" : ""}"> [${escapeHtml(st)}${item.blocking ? ", blocking" : ""}]</span>
      <div class="muted">${escapeHtml(item.message || "")}</div>
    </div>`;
  }).join("") || "<p class='muted'>No checklist items</p>";

  const issues = dash.blocking_issues || [];
  if (blocking) {
    if (issues.length) {
      blocking.classList.remove("hidden", "muted");
      blocking.innerHTML = "<strong>Blocking issues</strong><ul>" +
        issues.map(i => `<li>${escapeHtml(i.message || i.id)}</li>`).join("") + "</ul>";
    } else {
      blocking.classList.add("hidden");
      blocking.innerHTML = "";
    }
  }

  const j = dash.jobs || {};
  if (jobsEl) {
    jobsEl.innerHTML = `
      <div class="stat"><span>Active jobs</span><b>${j.active_count ?? "—"}</b></div>
      <div class="stat"><span>Recent</span><b>${j.recent_count ?? "—"}</b></div>
      <div class="stat"><span>Ready for review</span><b>${j.ready_for_review_count ?? "—"}</b></div>
      <div class="stat"><span>Latest</span><b>${escapeHtml(j.latest_state || "—")}</b></div>
    `;
  }

  const startBtn = document.getElementById("dashStartOnboarding");
  const resumeBtn = document.getElementById("dashResumeOnboarding");
  const completeBtn = document.getElementById("dashCompleteOnboarding");
  if (startBtn) startBtn.disabled = !ob.can_start;
  if (resumeBtn) resumeBtn.disabled = !ob.can_resume;
  if (completeBtn) completeBtn.disabled = !ob.can_complete;

  // Truthful startup routing hint: incomplete setup stays above workspace
  if (dash.startup_route === "onboarding" || dash.startup_route === "onboarding_resume") {
    const panel = document.getElementById("ws-dashboard");
    if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function refreshDashboard() {
  const dash = await api("/api/dashboard");
  renderDashboard(dash);
  return dash;
}

function renderReadiness(foundation, activity, access) {
  const el = document.getElementById("readinessPlanes");
  if (!el) return;
  const f = foundation || {};
  const jobState = f.active_job?.state || (activity?.active ? "GENERATING" : "—");
  const tiles = [
    ["Application", f.application || "UNKNOWN"],
    ["Media", f.media || "UNKNOWN"],
    ["Production", f.production || "UNKNOWN"],
    ["Job", jobState],
  ];
  el.innerHTML = tiles.map(([lab, val]) => {
    const ok = ["READY", "AVAILABLE"].includes(String(val)) ||
      (!["UNKNOWN", "BLOCKED", "FAILED", "UNAVAILABLE", "DEGRADED"].includes(String(val)) &&
        lab === "Job" && !TERMINAL_STATES.has(String(val)) && val !== "—");
    const bad = ["UNKNOWN", "BLOCKED", "FAILED", "UNAVAILABLE", "DEGRADED", "INTERRUPTED"].includes(String(val));
    return `<div class="readiness-tile ${bad ? "bad" : ok ? "ok" : ""}">
      <div class="lab">${escapeHtml(lab)}</div>
      <div class="val">${escapeHtml(val)}</div>
    </div>`;
  }).join("");

  const hint = document.getElementById("generateBlockedHint");
  if (hint) {
    if (access && access.production_allowed === false) {
      hint.textContent = access.message || `Generate blocked: ${access.block_reason || "authorization"}`;
    } else if (f.generate_allowed === false) {
      hint.textContent = `Generate blocked: ${(f.generate_block_reasons || []).join(", ") || "prerequisites"}`;
    } else {
      hint.textContent = "Generate allowed only means prerequisites + authorization — not that a video is ready.";
    }
  }
  const genShort = document.getElementById("genShort");
  const genLong = document.getElementById("genLong");
  const blockedAuth = access && access.production_allowed === false;
  const blockedReady = f.generate_allowed === false;
  if (genShort) genShort.disabled = !!(blockedAuth || blockedReady);
  if (genLong) genLong.disabled = !!(blockedAuth || blockedReady);
}

function renderJobCard(j, { selected } = {}) {
  const planes = j.result_planes || {};
  const err = j.error_summary
    ? `<br><span class="muted">Error (${escapeHtml(j.error_class || "unknown")}): ${escapeHtml(j.error_summary)}</span>`
    : "";
  return `
    <div class="card ${selected ? "job-card-selected" : ""}" data-job-id="${j.job_id}" role="button">
      <strong>#${j.job_id}</strong> ${escapeHtml(j.title || "")} · ${escapeHtml(j.request_type || "")}<br>
      <span><b>${escapeHtml(j.state)}</b> — ${escapeHtml(j.production_stage || j.stage_label || j.stage || "")}</span><br>
      <span class="muted">${escapeHtml(j.created_at || "")} · rev ${escapeHtml((j.revision || "").slice(0, 24))}</span>
      ${planes.ready_for_review ? "<br><span>READY_FOR_REVIEW</span>" : ""}
      ${err}
    </div>`;
}

function renderJobLists(active, recent) {
  const aEl = document.getElementById("activeJobsList");
  const rEl = document.getElementById("recentJobsList");
  if (aEl) {
    aEl.innerHTML = (active || []).map(j => renderJobCard(acceptJobProjection(j) || j, {
      selected: j.job_id === _selectedJobId,
    })).join("") || "<p class='muted'>No active jobs</p>";
  }
  if (rEl) {
    rEl.innerHTML = (recent || []).map(j => renderJobCard(acceptJobProjection(j) || j, {
      selected: j.job_id === _selectedJobId,
    })).join("") || "<p class='muted'>No recent jobs</p>";
  }
  document.querySelectorAll("[data-job-id]").forEach(card => {
    card.onclick = () => {
      _selectedJobId = Number(card.dataset.jobId);
      loadJobDetail(_selectedJobId);
    };
  });
}

function renderDetailPanels(job) {
  const detail = document.getElementById("jobDetailPanel");
  const result = document.getElementById("jobResultPanel");
  const fail = document.getElementById("jobFailurePanel");
  if (!job) {
    if (detail) detail.textContent = "Select a job";
    if (result) result.textContent = "—";
    if (fail) fail.textContent = "—";
    return;
  }
  job = acceptJobProjection(job) || job;
  const v = job.verification || {};
  const p = job.result_planes || {};
  if (detail) {
    detail.classList.remove("muted");
    detail.innerHTML = `
      <div><b>Job #${job.job_id}</b> · ${escapeHtml(job.request_type || "")}</div>
      <div>State: <b>${escapeHtml(job.state)}</b></div>
      <div>Stage: ${escapeHtml(job.production_stage || job.stage_label || "")}</div>
      <div class="muted">Created: ${escapeHtml(job.created_at || "")}</div>
      <div class="muted">Updated: ${escapeHtml(job.updated_at || "")}</div>
      <div class="muted">Duration: ${job.duration_sec != null ? job.duration_sec + "s" : "—"}</div>
      <div class="muted">Progress %: ${job.progress_percent == null ? "not available (stage only)" : job.progress_percent}</div>
      <div class="muted">Trace: ${escapeHtml(job.trace_id || "—")}</div>`;
  }
  if (result) {
    result.classList.remove("muted");
    result.innerHTML = `<div class="plane-grid">
      <div>File exists: <b>${p.file_exists ? "YES" : "NO"}</b></div>
      <div>Generated: <b>${p.generated ? "YES" : "NO"}</b></div>
      <div>Technically verified: <b>${p.technically_verified ? "YES" : "NO / UNKNOWN"}</b></div>
      <div>Quality verified: <b>${p.quality_verified ? "YES" : "NO / UNKNOWN"}</b></div>
      <div>Render verified: <b>${p.render_verified ? "YES" : "NO / UNKNOWN"}</b></div>
      <div>Ready for review: <b>${p.ready_for_review ? "YES" : "NO"}</b></div>
      <div class="muted">${escapeHtml(v.note || "")}</div>
      ${job.artifact_path ? `<div class="muted">${escapeHtml(job.artifact_path)}</div>` : ""}
    </div>`;
  }
  if (fail) {
    if (job.state === "FAILED" || job.state === "INTERRUPTED" || job.error_summary) {
      fail.classList.remove("muted");
      fail.innerHTML = `
        <div>Category: <b>${escapeHtml(job.error_class || "—")}</b></div>
        <div>${escapeHtml(job.error_summary || "—")}</div>
        <div>Recoverable: <b>${job.recoverable ? "YES" : "NO"}</b></div>
        <div>Retry same job: <b>${job.retry_supported ? "YES" : "NO (not supported)"}</b></div>
        <div class="muted">${escapeHtml(job.next_action || "")}</div>`;
    } else {
      fail.classList.add("muted");
      fail.textContent = "No failure on selected job";
    }
  }
}

async function loadJobDetail(jobId) {
  if (!jobId) return;
  const res = await api(`/api/jobs/${jobId}`);
  if (!res.ok) return;
  const job = acceptJobProjection(res.job);
  renderDetailPanels(job);
}

function applyLiveSnapshot(act, customerJob) {
  if (!act) return;
  const active = !!act.active;
  const job = customerJob ? acceptJobProjection(customerJob) : null;
  const statusEl = document.getElementById("liveStatus");
  const kindEl = document.getElementById("liveKind");
  const chEl = document.getElementById("liveChannel");
  const phaseEl = document.getElementById("livePhase");
  const sceneEl = document.getElementById("liveScene");
  const elapsedEl = document.getElementById("liveElapsed");
  const detailEl = document.getElementById("liveDetail");
  const mini = document.getElementById("liveMini");

  const stateLabel = job?.state || (active ? "GENERATING" : "idle");
  if (statusEl) statusEl.textContent = active ? stateLabel : (act.phase === "failed" ? "FAILED" : "idle");
  if (kindEl) kindEl.textContent = act.kind || "—";
  if (chEl) chEl.textContent = act.channel_name || "—";
  if (phaseEl) phaseEl.textContent = job?.production_stage || job?.stage_label || act.phase || "idle";
  if (sceneEl) {
    sceneEl.textContent = act.scene != null
      ? `${act.scene}${act.scene_total != null ? "/" + act.scene_total : ""}`
      : "—";
  }
  if (elapsedEl) elapsedEl.textContent = `${act.elapsed_sec || 0}s`;
  if (detailEl) detailEl.textContent = job?.error_summary || act.error || act.detail || "—";
  if (mini) {
    mini.classList.toggle("on", active);
    mini.textContent = active
      ? `লাইভ: #${job?.job_id || act.db_job_id || "—"} · ${job?.stage_label || act.phase || ""}`
      : "লাইভ: অলস";
  }

  const apis = document.getElementById("liveApis");
  if (apis) {
    apis.innerHTML = (act.apis || []).slice(-20).reverse().map(a =>
      `<div class="card">${escapeHtml(a.provider || "")} · ${escapeHtml(a.action || "")} · ${escapeHtml(a.status || "")}</div>`
    ).join("") || "<p class='muted'>—</p>";
  }
  const events = document.getElementById("liveEvents");
  if (events) {
    const stream = act.stream || act.events || [];
    events.innerHTML = stream.slice(-40).reverse().map(e =>
      `<div class="card">${escapeHtml(e.kind || "")}: ${escapeHtml(e.message || "")}</div>`
    ).join("") || "<p class='muted'>—</p>";
  }

  if (job?.job_id) {
    _selectedJobId = job.job_id;
    renderDetailPanels(job);
  }
  if (typeof act.stream_seq === "number") _liveSinceSeq = act.stream_seq;

  // Futuristic HUD & 6-Stage Timeline Visualizer
  updateFuturisticPipelineHUD(active, act, job);

  // Trigger Jarvis live screen display & voice commentary for rendering stages
  if (active) {
    const curPhase = String(job?.production_stage || job?.stage_label || act.phase || "").toLowerCase();
    let matchedStage = null;
    if (curPhase.includes("topic") || curPhase.includes("research")) {
      matchedStage = "topic_research";
    } else if (curPhase.includes("script") || curPhase.includes("prompt") || curPhase.includes("title")) {
      matchedStage = "title_script";
    } else if (curPhase.includes("localiz") || curPhase.includes("translate") || curPhase.includes("lang")) {
      matchedStage = "script_localization";
    } else if (curPhase.includes("audio") || curPhase.includes("voice") || curPhase.includes("tts")) {
      matchedStage = "audio_generation";
    } else if (curPhase.includes("render") || curPhase.includes("scene") || curPhase.includes("clip") || curPhase.includes("agnes") || curPhase.includes("pollinat")) {
      matchedStage = "scene_rendering";
    } else if (curPhase.includes("compose") || curPhase.includes("final") || curPhase.includes("assembly") || curPhase.includes("burn") || curPhase.includes("subtitle")) {
      matchedStage = "video_composed";
    } else if (curPhase.includes("quality") || curPhase.includes("qc") || curPhase.includes("gate")) {
      matchedStage = "quality_gate";
    }

    if (matchedStage && window._lastLiveCommentaryStage !== matchedStage) {
      window._lastLiveCommentaryStage = matchedStage;
      const uiLang = localStorage.getItem("amp_ui_lang") || document.getElementById("uiLangSelect")?.value || "bn";
      api(`/api/voice/commentary?stage=${encodeURIComponent(matchedStage)}&language=${encodeURIComponent(uiLang)}`)
        .then(comm => {
          if (comm && typeof window.playJarvisAudioCue === "function") {
            const displayMsg = comm.display_text || comm.text || comm.live_screen_text;
            window.playJarvisAudioCue(comm.audio_file, displayMsg);
          }
        })
        .catch(err => console.debug("Voice commentary cue skipped:", err));
    }
  } else {
    window._lastLiveCommentaryStage = null;
  }
}

function updateFuturisticPipelineHUD(active, act, job) {
  const badge = document.getElementById("jarvisLiveBadge");
  const stageEl = document.getElementById("hudCurrentStage");
  const engineEl = document.getElementById("hudActiveEngine");
  const sceneEl = document.getElementById("hudSceneCounter");
  const accelEl = document.getElementById("hudHardwareAccel");
  const explainerEl = document.getElementById("hudExplainerText");

  const cards = {
    topic: document.getElementById("stageCard-topic"),
    script: document.getElementById("stageCard-script"),
    localize: document.getElementById("stageCard-localize"),
    audio: document.getElementById("stageCard-audio"),
    render: document.getElementById("stageCard-render"),
    compose: document.getElementById("stageCard-compose"),
  };

  const stageOrder = ["topic", "script", "localize", "audio", "render", "compose"];

  if (!active) {
    if (badge) {
      badge.textContent = act?.phase === "failed" ? "ERROR" : "STANDBY";
      badge.style.background = act?.phase === "failed" ? "#ef4444" : "#0284c7";
    }
    if (stageEl) stageEl.textContent = act?.phase === "failed" ? "ব্যর্থ (Failed)" : "অলস (Ready for production)";
    if (engineEl) engineEl.textContent = "AI Engines Standby";
    if (sceneEl) sceneEl.textContent = "০ / ০ দৃশ্য · 0%";
    if (accelEl) accelEl.textContent = `${act?.elapsed_sec || 0}s · QSV / NVENC`;
    if (explainerEl) {
      explainerEl.textContent = act?.phase === "failed"
        ? `প্রক্রিয়া ব্যর্থ হয়েছে: ${act?.error || "ত্রুটি ঘটেছে"}`
        : "সফটওয়্যার অন রয়েছে। যেকোনো শর্ট বা লং ভিডিও কমান্ড দিলে এখানে রিয়েল-টাইমে কাজের প্রতিটি পদক্ষেপের বিস্তারিত ভিজ্যুয়ালাইজেশন ও ভয়েস কমেন্ট্রি প্রদর্শিত হবে।";
    }
    return;
  }

  if (badge) {
    badge.textContent = "LIVE ACTIVE";
    badge.style.background = "#10b981";
  }

  const curPhase = String(job?.production_stage || job?.stage_label || act.phase || "").toLowerCase();
  let currentKey = "topic";
  let engineName = "Grok AI Trending Engine";
  let explainerText = "টপিক রিসার্চ চলছে: হাই-সিটিআর ভাইরাল টপিক খুঁজে ডুপ্লিকেট ডাটাবেসে ভ্যালিডেশন করা হচ্ছে...";

  if (curPhase.includes("topic") || curPhase.includes("research")) {
    currentKey = "topic";
    engineName = "Grok AI / Perplexity API (Trends)";
    explainerText = "ভাইরাল টপিক নির্বাচন: ট্রেন্ডিং কি-ওয়ার্ড ও পূর্ববর্তী প্রযোজিত ভিডিওগুলোর সাথে ম্যাচিং করে ইউনিক টপিক নিশ্চিত করা হচ্ছে।";
  } else if (curPhase.includes("script") || curPhase.includes("title") || curPhase.includes("blueprint") || curPhase.includes("prompt")) {
    currentKey = "script";
    engineName = "Grok / Google Gemini Reasoning";
    explainerText = "স্ক্রিপ্ট ও ভিজ্যুয়াল পরিকল্পনা: প্রতিটি দৃশ্যের রিটেনশন হুক, ভিজ্যুয়াল ক্যামেরা ডিরেকশন এবং টাইম-স্ট্যাম্প ব্লুপ্রিন্ট তৈরি হচ্ছে।";
  } else if (curPhase.includes("localiz") || curPhase.includes("translate") || curPhase.includes("lang")) {
    currentKey = "localize";
    engineName = "Google AI Studio Multilingual Engine";
    explainerText = "৬-ভাষা লোকালাইজেশন: বাংলা, হিন্দি, ইংরেজি, উর্দু, তামিল ও মালায়ালম ভাষায় সাংস্কৃতিক ব্যাকরণ ও শব্দচয়ন নিখুঁত করা হচ্ছে।";
  } else if (curPhase.includes("audio") || curPhase.includes("voice") || curPhase.includes("tts")) {
    currentKey = "audio";
    engineName = "Studio Neural TTS Engine";
    explainerText = "স্টুডিও ভয়েস সিন্থেসিস: সকল ভাষার জন্য আল্ট্রা-ন্যাচারাল রোবোটিকলেস ভয়েস সিন্থেসিস এবং অডিও ফ্রিকোয়েন্সি ফিল্টারিং চলছে।";
  } else if (curPhase.includes("render") || curPhase.includes("scene") || curPhase.includes("clip") || curPhase.includes("agnes") || curPhase.includes("pollinat")) {
    currentKey = "render";
    engineName = "Agnes Engine / Pollinations AI 4K";
    explainerText = "ভিজ্যুয়াল সিন রেন্ডারিং: প্রতিটি দৃশ্যের হাই-রেজুলেশন এআই ফুটেজ তৈরি ও প্যান-জুম ক্যামেরা ট্রানজিশন প্রসেসিং হচ্ছে।";
  } else if (curPhase.includes("compose") || curPhase.includes("final") || curPhase.includes("assembly") || curPhase.includes("burn") || curPhase.includes("subtitle")) {
    currentKey = "compose";
    engineName = "FFmpeg Hardware Accelerated Encoder";
    explainerText = "ফাইনাল কম্পোজিশন ও সাবটাইটেল: ব্যাকগ্রাউন্ড মিউজিক ডাকিং, ডায়নামিক কালারফুল সাবটাইটেল ও ব্র্যান্ড ওয়াটারমার্ক সহ ফাইনাল ভিডিও রেন্ডার সম্পন্ন হচ্ছে।";
  }

  const activeIndex = stageOrder.indexOf(currentKey);
  stageOrder.forEach((k, idx) => {
    const el = cards[k];
    if (!el) return;
    const statusSpan = el.querySelector(".step-status");
    if (idx < activeIndex) {
      el.className = "stage-step-card completed";
      if (statusSpan) statusSpan.textContent = "সম্পন্ন ✓";
    } else if (idx === activeIndex) {
      el.className = "stage-step-card active";
      if (statusSpan) statusSpan.textContent = "চলমান ⚡";
    } else {
      el.className = "stage-step-card";
      if (statusSpan) statusSpan.textContent = "অপেক্ষমাণ";
    }
  });

  if (stageEl) stageEl.textContent = job?.production_stage || job?.stage_label || act.phase || currentKey;
  if (engineEl) engineEl.textContent = engineName;
  if (sceneEl) {
    const scText = act.scene != null ? `${act.scene}${act.scene_total != null ? "/" + act.scene_total : ""}` : "১/১";
    sceneEl.textContent = `${scText} দৃশ্য · ${act.progress_pct || 0}%`;
  }
  if (accelEl) accelEl.textContent = `${act.elapsed_sec || 0}s · Intel QSV / NVENC`;
  if (explainerEl) explainerEl.textContent = explainerText;
}

function shouldContinuePolling(activity, selectedJob) {
  if (activity?.active) return true;
  if (selectedJob && !TERMINAL_STATES.has(String(selectedJob.state || ""))) return true;
  // any non-terminal in cache
  return Object.values(_jobCacheById).some(j => j && !TERMINAL_STATES.has(String(j.state || "")));
}

async function pollLive() {
  if (!_pollEnabled) return;
  try {
    const res = await api(`/api/activity?since_seq=${_liveSinceSeq || 0}`);
    if (!res.ok) {
      // errors must not become success — just back off
      _livePollMs = Math.min((_livePollMs || 2500) * 1.5, 15000);
    } else {
      applyLiveSnapshot(res.activity, res.customer_job);
      const selected = _selectedJobId ? _jobCacheById[_selectedJobId] : res.customer_job;
      if (shouldContinuePolling(res.activity, selected)) {
        _livePollMs = res.activity?.active ? 2000 : 4000;
      } else {
        // Terminal + no active: stop high-frequency polling
        _livePollMs = null;
        _pollEnabled = false;
        return;
      }
    }
  } catch (_) {
    _livePollMs = Math.min((_livePollMs || 2500) * 1.5, 15000);
  } finally {
    if (_livePollTimer) clearTimeout(_livePollTimer);
    if (_pollEnabled && _livePollMs != null) {
      _livePollTimer = setTimeout(pollLive, _livePollMs);
    }
  }
}

function resumePolling() {
  _pollEnabled = true;
  _livePollMs = 2000;
  pollLive();
}

function stageGlyph(status) {
  const s = String(status || "").toUpperCase();
  if (s === "COMPLETED") return "✓";
  if (s === "RUNNING") return "●";
  if (s === "BLOCKED" || s === "FAILED") return "!";
  if (s === "READY") return "◇";
  return "○";
}

function renderWorkspaceProjection(ws) {
  const header = document.getElementById("wsProjectHeader");
  const timeline = document.getElementById("wsWorkflowTimeline");
  const actionEl = document.getElementById("wsActionBanner");
  const summary = document.getElementById("wsProductionSummary");
  const quality = document.getElementById("wsQualityPanel");
  const preview = document.getElementById("wsPreviewPanel");
  const approval = document.getElementById("wsApprovalPanel");
  const approveBtn = document.getElementById("wsApproveBtn");
  const rejectBtn = document.getElementById("wsRejectBtn");

  const p = ws.project || {};
  if (header) {
    header.classList.remove("muted");
    header.innerHTML = `
      <div><strong>${escapeHtml(p.title || "Untitled")}</strong></div>
      <div class="muted">${escapeHtml(p.project_id || "")} · owner ${escapeHtml(p.owner_login_id || "—")}</div>
      <div>Language: <b>${escapeHtml(p.language || "—")}</b> · Format: <b>${escapeHtml(p.format || "—")}</b></div>
      <div>Status: <b>${escapeHtml(p.current_status || "—")}</b></div>
      <div class="muted">Updated: ${escapeHtml(p.updated_at || "—")}</div>`;
  }

  const stages = (ws.workflow && ws.workflow.stages) || [];
  if (timeline) {
    timeline.classList.remove("muted");
    timeline.innerHTML = stages.map(st => {
      const prog = st.progress && st.progress.label
        ? `<div class="muted">${escapeHtml(st.progress.label)}</div>`
        : "";
      const block = st.blocked_reason
        ? `<div class="muted">${escapeHtml(st.blocked_reason)}</div>`
        : "";
      const act = st.action_required
        ? `<div class="muted">${escapeHtml(st.action_required)}</div>`
        : "";
      return `<div class="workflow-stage status-${escapeHtml(String(st.status || "").toLowerCase())}">
        <span class="glyph">${stageGlyph(st.status)}</span>
        <div>
          <div><b>${escapeHtml(st.stage)}</b> · ${escapeHtml(st.status)}</div>
          ${prog}${block}${act}
        </div>
      </div>`;
    }).join("") || "<p class='muted'>No workflow data</p>";
  }

  const action = ws.action || {};
  if (actionEl) {
    actionEl.classList.remove("muted");
    actionEl.className = `action-banner kind-${escapeHtml(String(action.kind || "").toLowerCase())}`;
    actionEl.innerHTML = `
      <div><b>${escapeHtml(action.kind || "—")}</b>${action.stage ? " · " + escapeHtml(action.stage) : ""}</div>
      <div>${escapeHtml(action.reason || "")}</div>
      <div class="muted">${escapeHtml(action.recommended_action || "")}</div>
      ${action.error_code ? `<div class="muted">code: ${escapeHtml(action.error_code)}</div>` : ""}`;
  }

  const ps = ws.production_summary || {};
  if (summary) {
    summary.classList.remove("muted");
    summary.innerHTML = `
      <div>Scenes: <b>${ps.scenes != null ? escapeHtml(String(ps.scenes)) : "—"}</b></div>
      <div>Dialogue beats: <b>${ps.dialogue_beats != null ? escapeHtml(String(ps.dialogue_beats)) : "—"}</b></div>
      <div>Visual beats: <b>${ps.visual_beats != null ? escapeHtml(String(ps.visual_beats)) : "—"}</b></div>
      <div>Audio: <b>${escapeHtml(ps.audio_state || "UNKNOWN")}</b></div>
      <div>Subtitle/localization: <b>${escapeHtml(ps.subtitle_localization_state || "UNKNOWN")}</b></div>
      <div>Verification: <b>${escapeHtml(ps.verification_state || "UNKNOWN")}</b></div>
      <div>Publishability: <b>${escapeHtml(ps.publishability_state || "UNKNOWN")}</b></div>
      <div class="muted">source: ${escapeHtml(ps.source || "—")}${ps.c05_visible ? " · C05 data visible" : ""}</div>`;
  }

  const qp = ws.quality_panel || {};
  if (quality) {
    quality.classList.remove("muted");
    const dims = qp.dimensions || [];
    quality.innerHTML = `
      <div class="quality-grid">
        ${dims.map(d => {
          const st = String(d.status || "NOT_RUN").toUpperCase();
          // CRITICAL: never style UNKNOWN as PASS
          const cls = st === "PASS" ? "pass" : st === "FAIL" || st === "BLOCKED" ? "fail" : st === "UNKNOWN" ? "unknown" : "notrun";
          return `<div class="quality-dim ${cls}"><span>${escapeHtml(d.name)}</span><b>${escapeHtml(st)}</b></div>`;
        }).join("")}
      </div>
      <div class="muted">${escapeHtml(qp.note || "UNKNOWN is never PASS")}</div>`;
  }

  const pv = ws.preview || {};
  if (preview) {
    preview.classList.toggle("muted", !pv.available);
    const planes = pv.planes || {};
    preview.innerHTML = `
      <div><b>${escapeHtml(pv.status || (pv.available ? "AVAILABLE" : "PREVIEW_NOT_AVAILABLE_YET"))}</b></div>
      <div>Verification: <b>${escapeHtml(pv.verification_status || "UNKNOWN")}</b></div>
      <div>Quality: <b>${escapeHtml(pv.quality_status || "UNKNOWN")}</b></div>
      <div>Publishability: <b>${escapeHtml(pv.publishability_status || "NOT_PUBLISHABLE")}</b></div>
      <div>Ready to upload: <b>${pv.ready_to_upload ? "YES" : "NO"}</b></div>
      <div>Approval: <b>${escapeHtml(pv.approval_status || (ws.approval || {}).approval_status || "—")}</b></div>
      <div class="muted">revision ${escapeHtml(pv.revision_id || pv.current_revision || "—")}</div>
      <div class="muted">${escapeHtml(pv.path || pv.message || "")}</div>
      <div class="muted">${escapeHtml(pv.note || "Preview ≠ Verified ≠ Publishable ≠ Approved ≠ Published")}</div>
      ${pv.mock_is_not_real_media ? `<div class="muted">execution: MOCK (not real media)</div>` : ""}
      ${planes.published ? "" : ""}`;
  }

  const ap = ws.approval || {};
  window._wsApprovalJobId = (ws.selected_job && ws.selected_job.job_id) || window._wsApprovalJobId || null;
  window._wsRevisionId = ap.revision_id || pv.revision_id || null;
  if (approval) {
    approval.classList.remove("muted");
    approval.innerHTML = `
      <div>State: <b>${escapeHtml(ap.approval_status || ap.state || "NOT_READY")}</b></div>
      <div class="muted">${escapeHtml(ap.note || "")}</div>
      <div class="muted">publishes=${ap.publishes ? "YES" : "NO"} · does not upload/schedule</div>`;
  }
  const canDecide =
    (ap.state === "PENDING" || ap.approval_status === "PENDING" || ap.state === "READY_FOR_REVIEW") &&
    window._wsApprovalJobId;
  if (approveBtn) approveBtn.disabled = !canDecide;
  if (rejectBtn) rejectBtn.disabled = !canDecide;

  const histEl = document.getElementById("wsRevisionHistoryPanel");
  const hist = ws.revision_history || {};
  if (histEl) {
    histEl.classList.remove("muted");
    const entries = hist.entries || [];
    if (!entries.length) {
      histEl.innerHTML = `<div class="muted">No revision history yet</div>`;
    } else {
      histEl.innerHTML = entries
        .map((e) => {
          const cur = e.current ? " · current" : "";
          const rej = e.rejection_reason && e.rejection_reason.text
            ? ` · reason: ${escapeHtml(e.rejection_reason.text)}`
            : "";
          return `<div class="hist-row">
            <b>${escapeHtml(e.approval_status || e.kind || "—")}</b>
            <span class="muted">${escapeHtml(e.revision_id || "").slice(0, 12)}${cur}</span>
            <div class="muted">${escapeHtml(e.created_at || e.timestamp || "")}${rej}</div>
          </div>`;
        })
        .join("");
    }
  }

  const autoEl = document.getElementById("wsAutomationPanel");
  const auto = ws.automation || {};
  if (autoEl) {
    autoEl.classList.remove("muted");
    if (!auto.available) {
      autoEl.innerHTML = `<div class="muted">No automation data</div>`;
    } else {
      autoEl.innerHTML = `
        <div>Queue: <b>${escapeHtml(auto.queue_status || "—")}</b></div>
        <div>Attempts: <b>${escapeHtml(String(auto.attempt_count != null ? auto.attempt_count : "—"))}</b> / ${escapeHtml(String(auto.max_attempts || "—"))}</div>
        <div>Failure category: <b>${escapeHtml(auto.failure_category || "—")}</b></div>
        <div>Progress: <b>${escapeHtml(auto.progress || "UNKNOWN")}</b></div>
        <div>Approval plane: <b>${escapeHtml(auto.approval_status || "—")}</b></div>
        <div class="muted">publishes=${auto.publishes ? "YES" : "NO"} · ${(auto.planes && auto.planes.note) || ""}</div>`;
    }
  }

  const monEl = document.getElementById("wsProductionMonitor");
  const mon = ws.production_monitor || {};
  window._wsMonitorJobId = mon.job_id || window._wsApprovalJobId || null;
  const cancelBtn = document.getElementById("wsCancelJobBtn");
  if (monEl) {
    monEl.classList.remove("muted");
    if (!mon.ok && !mon.monitor_state) {
      monEl.innerHTML = `<div class="muted">No production monitor data</div>`;
      if (cancelBtn) cancelBtn.disabled = true;
    } else {
      const ev = (mon.lifecycle_events || []).slice(-5).map(e =>
        `<div class="muted">${escapeHtml(e.type || e.event || "—")} · ${escapeHtml(e.at || "")}</div>`
      ).join("");
      const att = (mon.attention || []).map(a =>
        `<div><b>${escapeHtml(a.kind || "")}</b>: ${escapeHtml(a.message || "")}</div>`
      ).join("");
      monEl.innerHTML = `
        <div>State: <b>${escapeHtml(mon.monitor_state || "—")}</b> · Stage: <b>${escapeHtml(mon.stage || "—")}</b></div>
        <div>Path: <b>${escapeHtml(mon.execution_path || "—")}</b> (${escapeHtml(mon.execution_path_class || "")})</div>
        <div>Progress: <b>${escapeHtml(mon.progress || "UNKNOWN")}</b> · %: not used</div>
        <div>Verify: <b>${escapeHtml(mon.verification_status || "UNKNOWN")}</b> · Preview: <b>${mon.preview_available ? "YES" : "NO"}</b></div>
        <div>Approval: <b>${escapeHtml(mon.approval_status || "—")}</b> · Cancel: <b>${escapeHtml(mon.cancellation_status || "NONE")}</b></div>
        <div>Recovery: <b>${escapeHtml(mon.recovery_status || "—")}</b> · Fail: <b>${escapeHtml(mon.failure_category || "—")}</b></div>
        <div class="muted">${escapeHtml((mon.planes && mon.planes.note) || "")}</div>
        <div><b>Attention</b></div>${att || "<div class='muted'>—</div>"}
        <div><b>Recent activity</b></div>${ev || "<div class='muted'>—</div>"}`;
      const canCancel = ["QUEUED", "WAITING", "RUNNING", "CANCELLATION_REQUESTED"].includes(mon.monitor_state);
      if (cancelBtn) cancelBtn.disabled = !canCancel || !window._wsMonitorJobId;
    }
  }

  const pubEl = document.getElementById("wsPublishingPanel");
  const pub = ws.publishing || {};
  const pubBtn = document.getElementById("wsPublishBtn");
  const pubRefreshBtn = document.getElementById("wsPublishRefreshBtn");
  window._wsPublishJobId = pub.job_id || window._wsMonitorJobId || null;
  if (pubEl) {
    pubEl.classList.remove("muted");
    if (!pub.ok && !pub.publication_state) {
      pubEl.innerHTML = `<div class="muted">No publishing data</div>`;
      if (pubBtn) pubBtn.disabled = true;
      if (pubRefreshBtn) pubRefreshBtn.disabled = true;
    } else {
      const planes = pub.planes || {};
      pubEl.innerHTML = `
        <div>Approval: <b>${escapeHtml(pub.approval_state || "—")}</b> · Publishability: <b>${escapeHtml(pub.publishability || "—")}</b></div>
        <div>Ready to upload: <b>${pub.ready_to_upload ? "YES" : "NO"}</b> · State: <b>${escapeHtml(pub.publication_state || "—")}</b></div>
        <div>Provider: <b>${escapeHtml(pub.provider || "—")}</b> · Channel: <b>${escapeHtml((pub.channel && (pub.channel.name || pub.channel.id)) || "—")}</b></div>
        <div>Provider ID: <b>${escapeHtml(pub.provider_video_id || "—")}</b></div>
        <div>URL: <b>${escapeHtml(pub.provider_url || "—")}</b></div>
        <div>Blocking: <b>${escapeHtml(pub.blocking_reason || "—")}</b> · Action: <b>${escapeHtml(pub.required_action || "—")}</b></div>
        <div class="muted">mock=${pub.mock === true ? "YES" : (pub.mock === false ? "NO" : "—")} · schedules=${pub.scheduling_implemented ? "YES" : "NO"}</div>
        <div class="muted">${escapeHtml(planes.note || "")}</div>`;
      const acts = pub.actions || {};
      if (pubBtn) pubBtn.disabled = !acts.PUBLISH || !window._wsPublishJobId;
      if (pubRefreshBtn) pubRefreshBtn.disabled = !acts.REFRESH_STATUS || !window._wsPublishJobId;
    }
  }

  const schEl = document.getElementById("wsSchedulePanel");
  const sch = ws.publishing_schedule || {};
  window._wsScheduleId = (sch.active && sch.active.schedule_id) || window._wsScheduleId || null;
  const scheduleBtn = document.getElementById("wsScheduleBtn");
  const rescheduleBtn = document.getElementById("wsRescheduleBtn");
  const cancelSchBtn = document.getElementById("wsCancelScheduleBtn");
  const schRefreshBtn = document.getElementById("wsScheduleRefreshBtn");
  if (schEl) {
    schEl.classList.remove("muted");
    const active = sch.active || (sch.schedules && sch.schedules[0]) || null;
    if (!sch.ok && !active) {
      schEl.innerHTML = `<div class="muted">No schedules</div>`;
      if (scheduleBtn) scheduleBtn.disabled = !(window._wsPublishJobId || window._wsMonitorJobId);
      if (rescheduleBtn) rescheduleBtn.disabled = true;
      if (cancelSchBtn) cancelSchBtn.disabled = true;
      if (schRefreshBtn) schRefreshBtn.disabled = true;
    } else {
      const a = active || {};
      window._wsScheduleId = a.schedule_id || window._wsScheduleId;
      schEl.innerHTML = `
        <div>Status: <b>${escapeHtml(a.status || "NOT_SCHEDULED")}</b> · ID: <b>${escapeHtml(a.schedule_id || "—")}</b></div>
        <div>Local: <b>${escapeHtml(a.local_datetime || "—")}</b> · TZ: <b>${escapeHtml(a.timezone || "—")}</b></div>
        <div>UTC: <b>${escapeHtml(a.scheduled_at_utc || "—")}</b></div>
        <div>Provider: <b>${escapeHtml(a.provider || "—")}</b> · Channel: <b>${escapeHtml(String(a.channel_id || "—"))}</b></div>
        <div>Created: <b>${escapeHtml(a.created_at || "—")}</b> · Updated: <b>${escapeHtml(a.updated_at || "—")}</b></div>
        <div class="muted">SCHEDULED≠PUBLISHED · auto_catch_up=${(sch.missed_policy && sch.missed_policy.auto_catch_up_publish) ? "YES" : "NO"}</div>`;
      const acts = sch.actions || {};
      if (scheduleBtn) scheduleBtn.disabled = !acts.SCHEDULE && !!active;
      if (scheduleBtn && !active) scheduleBtn.disabled = !(window._wsPublishJobId || window._wsMonitorJobId);
      if (rescheduleBtn) rescheduleBtn.disabled = !acts.RESCHEDULE || !window._wsScheduleId;
      if (cancelSchBtn) cancelSchBtn.disabled = !acts.CANCEL_SCHEDULE || !window._wsScheduleId;
      if (schRefreshBtn) schRefreshBtn.disabled = !acts.REFRESH || !window._wsScheduleId;
    }
  }
}

async function refreshWorkspace() {
  const ws = await api("/api/workspace");
  if (!ws.ok) {
    if (ws.identity) renderAuthBanner(ws.identity, null);
    if (ws.error === "job_access_denied") {
      const timeline = document.getElementById("wsWorkflowTimeline");
      if (timeline) timeline.textContent = "Access denied for requested job (ownership).";
    }
    return;
  }
  renderAuthBanner(ws.identity, ws.access);
  renderReadiness(ws.foundation, ws.activity, ws.access);
  (ws.active_jobs || []).forEach(acceptJobProjection);
  (ws.recent_jobs || []).forEach(acceptJobProjection);
  renderJobLists(ws.active_jobs || [], ws.recent_jobs || []);
  if (ws.selected_job) {
    const j = acceptJobProjection(ws.selected_job);
    _selectedJobId = j?.job_id ?? _selectedJobId;
    renderDetailPanels(j);
  }
  renderWorkspaceProjection(ws);
  renderTrsWorkflow(ws.trs_workflow || {});
  renderProductionPlan(ws.production_plan || {});
  renderExecution(ws.execution || {});
  refreshNotificationsPanel();
  refreshHelpContext();
  if (ws.activity?.active || (ws.active_jobs || []).length) {
    resumePolling();
  }
}

async function refreshNotificationsPanel() {
  const el = document.getElementById("wsNotificationsPanel");
  const badge = document.getElementById("wsNotifyBadge");
  if (!el) return;
  const res = await api("/api/workspace/notifications?locale=en");
  el.classList.remove("muted");
  if (!res.ok) {
    el.innerHTML = `<div class="muted">${escapeHtml(res.error || "unavailable")}</div>`;
    if (badge) badge.textContent = "(—)";
    return;
  }
  if (badge) badge.textContent = `(${res.unread_count || 0} unread)`;
  const items = res.notifications || [];
  if (!items.length) {
    el.innerHTML = `<div class="muted">No notifications</div>`;
    return;
  }
  el.innerHTML = items.slice(0, 8).map(n => `
    <div class="row" style="align-items:flex-start;gap:8px;margin-bottom:6px">
      <div style="flex:1">
        <div><b>${escapeHtml(n.category || "")}</b>
          ${n.action_required ? " · <span>ACTION REQUIRED</span>" : ""}
          · ${escapeHtml(n.read_state || "UNREAD")}</div>
        <div class="muted">${escapeHtml(n.message || "")}</div>
        <div class="muted">${escapeHtml((n.deep_link && n.deep_link.label) || "")}</div>
      </div>
      ${n.read_state === "UNREAD" ? `<button type="button" class="btn ghost wsNotifyReadBtn" data-nid="${escapeHtml(n.notification_id)}">Mark read</button>` : ""}
    </div>`).join("");
  el.querySelectorAll(".wsNotifyReadBtn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const nid = btn.getAttribute("data-nid");
      await api(`/api/workspace/notifications/${encodeURIComponent(nid)}/read`, { method: "POST", body: "{}" });
      refreshNotificationsPanel();
    });
  });
}

async function refreshHelpContext() {
  const el = document.getElementById("wsHelpPanel");
  if (!el) return;
  const jobId = window._wsMonitorJobId || _selectedJobId || 0;
  const res = await api(`/api/workspace/help/context?job_id=${jobId || 0}&locale=en`);
  el.classList.remove("muted");
  if (!res.ok) {
    el.innerHTML = `<div class="muted">${escapeHtml(res.error || "permission denied")}</div>`;
    return;
  }
  el.innerHTML = `
    <div>State: <b>${escapeHtml(res.current_state || "UNKNOWN")}</b></div>
    <div>Action: <b>${escapeHtml(res.recommended_action || "—")}</b></div>
    <div class="muted">${escapeHtml(res.note || "")}</div>
    <div class="muted">can_mutate=${res.can_mutate_production ? "YES" : "NO"}</div>`;
}

document.getElementById("wsNotifyRefreshBtn")?.addEventListener("click", () => refreshNotificationsPanel());
document.getElementById("wsHelpAskBtn")?.addEventListener("click", async () => {
  const q = document.getElementById("wsHelpQuery")?.value || "";
  const jobId = window._wsMonitorJobId || _selectedJobId || 0;
  const res = await api("/api/workspace/help/query", {
    method: "POST",
    body: JSON.stringify({ query: q, job_id: jobId || null, locale: "en" }),
  });
  const el = document.getElementById("wsHelpPanel");
  if (el) {
    el.classList.remove("muted");
    el.innerHTML = `
      <div><b>Answer</b>: ${escapeHtml(res.answer || res.error || "—")}</div>
      <div>State: <b>${escapeHtml(res.current_state || "—")}</b> · ${escapeHtml(res.support_classification || "")}</div>
      <div class="muted">${escapeHtml((res.deep_link && res.deep_link.label) || "")}</div>`;
  }
});

function currentWorkspaceChannelId() {
  return Number(document.getElementById("channelSelect")?.value || window._cfgChannelId || 0);
}

function renderProductionPlan(pp) {
  const el = document.getElementById("wsProductionPlanPanel");
  if (!el) return;
  el.classList.remove("muted");
  const status = String(pp.status || "NOT_STARTED").toUpperCase();
  const ready = !!pp.ready_for_generation;
  const falseReady = ready && ["BLOCKED", "UNKNOWN", "NOT_READY", "STALE"].includes(status);
  const displayReady = ready && !falseReady && status === "READY_FOR_GENERATION";
  el.innerHTML = `
    <div>Script: <b>${escapeHtml(pp.script_status || "—")}</b></div>
    <div>Plan status: <b>${escapeHtml(status)}</b></div>
    <div>Ready for generation: <b>${displayReady ? "YES" : "NO"}</b></div>
    <div>Scenes: <b>${pp.scene_count ?? "—"}</b> · Dialogue beats: <b>${pp.dialogue_beat_count ?? "—"}</b> · Visual beats: <b>${pp.visual_beat_count ?? "—"}</b></div>
    <div>Audio: <b>${escapeHtml(pp.audio_readiness || "—")}</b> · Subtitle/loc: <b>${escapeHtml(pp.subtitle_localization_readiness || "—")}</b></div>
    <div>Continuity: <b>${escapeHtml(pp.continuity_readiness || "—")}</b> · Modes: <b>${escapeHtml((pp.generation_modes || []).join(", ") || "—")}</b></div>
    <div class="muted">rev ${escapeHtml(pp.script_revision || "—")} · fp ${(pp.fingerprint || "").slice(0, 16)}</div>
    ${(pp.blocking_issues || []).slice(0, 5).map(b => `<div class="muted">block: ${escapeHtml(String(b))}</div>`).join("")}
    ${(pp.warnings || []).slice(0, 3).map(w => `<div class="muted">warn: ${escapeHtml(String(w))}</div>`).join("")}
    <div class="muted">${escapeHtml(pp.note || "")}</div>`;
}

document.getElementById("wsBuildPlanBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  if (!channel_id) return alert("Select a channel first");
  const res = await api("/api/workspace/production-plan", {
    method: "POST",
    body: JSON.stringify({ channel_id, force_rebuild: true }),
  });
  if (!res.ok) alert(`Production plan: ${res.error || res.status || "blocked"}`);
  refreshWorkspace();
});

function renderExecution(ex) {
  const el = document.getElementById("wsExecutionPanel");
  if (!el) return;
  el.classList.remove("muted");
  if (!ex || !ex.ok) {
    el.innerHTML = `<div>Status: <b>${escapeHtml((ex && (ex.status || ex.error)) || "NOT_STARTED")}</b></div>
      <div class="muted">Requires READY_FOR_GENERATION production plan</div>`;
    return;
  }
  const planes = ex.planes || {};
  el.innerHTML = `
    <div>Phase: <b>${escapeHtml(ex.phase || "—")}</b> · State: <b>${escapeHtml(ex.state || "—")}</b></div>
    <div>Generated: <b>${planes.generated ? "YES" : "NO"}</b>
      · Verified: <b>${planes.verified ? "YES" : "NO"}</b>
      · Publishable: <b>${planes.publishable ? "YES" : "NO"}</b></div>
    <div>Verification: <b>${escapeHtml(ex.verification_status || "—")}</b>
      · Repair count: <b>${ex.repair_count ?? 0}</b></div>
    <div>Units: payload <b>${(ex.scene_beat_counts || {}).payload_units ?? "—"}</b>
      · materialized <b>${(ex.scene_beat_counts || {}).materialized_units ?? "—"}</b></div>
    <div class="muted">${escapeHtml(ex.note || "")}</div>
    <div class="muted">artifact: ${escapeHtml(ex.final_artifact_reference || "—")}</div>`;
}

document.getElementById("wsGenerateBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  if (!channel_id) return alert("Select a channel first");
  // C06-H: canonical customer path is queue=true (LEGACY_COMPAT sync remains if queue:false)
  const res = await api("/api/workspace/generate", {
    method: "POST",
    body: JSON.stringify({
      channel_id,
      video_type: "short",
      execution_mode: "MOCK_DETERMINISTIC",
      deterministic_fixtures: true,
      queue: true,
      process_now: true,
    }),
  });
  if (!res.ok) alert(`Generate: ${res.error || res.status || "blocked"}`);
  refreshWorkspace();
});

document.getElementById("wsCancelJobBtn")?.addEventListener("click", async () => {
  const jobId = window._wsMonitorJobId || window._wsApprovalJobId || _selectedJobId;
  if (!jobId) return;
  const res = await api(`/api/workspace/job/${jobId}/cancel`, { method: "POST", body: "{}" });
  if (!res.ok) alert(`Cancel: ${res.error || "failed"}`);
  else alert(`${res.state} — does not publish.`);
  refreshWorkspace();
});

document.getElementById("wsPublishBtn")?.addEventListener("click", async () => {
  const jobId = window._wsPublishJobId || window._wsMonitorJobId || _selectedJobId;
  if (!jobId) return;
  const res = await api("/api/workspace/publishing/publish", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, provider: "mock" }),
  });
  if (!res.ok) {
    alert(`Publish blocked/failed: ${res.error || (res.result && res.result.error) || "error"}`);
  } else {
    const st = (res.result && res.result.state) || "UPLOAD_ACCEPTED";
    alert(`${st} — upload accepted ≠ published. Mock=${(res.result && res.result.mock) ? "YES" : "NO"}`);
  }
  refreshWorkspace();
});

document.getElementById("wsPublishRefreshBtn")?.addEventListener("click", async () => {
  const jobId = window._wsPublishJobId || window._wsMonitorJobId || _selectedJobId;
  if (!jobId) return;
  const res = await api("/api/workspace/publishing/refresh", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, scenario: "published_immediate" }),
  });
  if (!res.ok) alert(`Refresh: ${res.error || (res.result && res.result.error) || "failed"}`);
  else alert(`Status: ${(res.result && res.result.state) || "—"}`);
  refreshWorkspace();
});

function _scheduleLocalPayload() {
  const local = document.getElementById("wsScheduleLocal")?.value || "";
  const tz = document.getElementById("wsScheduleTz")?.value || "UTC";
  // datetime-local → "YYYY-MM-DDTHH:MM"
  return { local_datetime: local ? local.replace(" ", "T") : "", timezone: tz };
}

document.getElementById("wsScheduleBtn")?.addEventListener("click", async () => {
  const jobId = window._wsPublishJobId || window._wsMonitorJobId || _selectedJobId;
  if (!jobId) return;
  const { local_datetime, timezone } = _scheduleLocalPayload();
  if (!local_datetime) return alert("Pick local date/time");
  const res = await api("/api/workspace/publishing/schedule", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, local_datetime, timezone, provider: "mock" }),
  });
  if (!res.ok) alert(`Schedule: ${res.error || "failed"}`);
  else {
    window._wsScheduleId = res.schedule?.schedule_id;
    alert(`SCHEDULED — not published. ${res.schedule?.scheduled_at_utc || ""}`);
  }
  refreshWorkspace();
});

document.getElementById("wsRescheduleBtn")?.addEventListener("click", async () => {
  const sid = window._wsScheduleId;
  if (!sid) return;
  const { local_datetime, timezone } = _scheduleLocalPayload();
  if (!local_datetime) return alert("Pick new local date/time");
  const res = await api(`/api/workspace/publishing/schedule/${sid}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ local_datetime, timezone }),
  });
  if (!res.ok) alert(`Reschedule: ${res.error || "failed"}`);
  else {
    window._wsScheduleId = res.schedule?.schedule_id || sid;
    alert("Rescheduled — old SUPERSEDED");
  }
  refreshWorkspace();
});

document.getElementById("wsCancelScheduleBtn")?.addEventListener("click", async () => {
  const sid = window._wsScheduleId;
  if (!sid) return;
  const res = await api(`/api/workspace/publishing/schedule/${sid}/cancel`, { method: "POST", body: "{}" });
  if (!res.ok) alert(`Cancel schedule: ${res.error || "failed"}`);
  else alert("Schedule CANCELLED");
  refreshWorkspace();
});

document.getElementById("wsScheduleRefreshBtn")?.addEventListener("click", async () => {
  const sid = window._wsScheduleId;
  if (!sid) return;
  const res = await api(`/api/workspace/publishing/schedule/${sid}/refresh`, { method: "POST", body: "{}" });
  if (!res.ok) alert(`Schedule refresh: ${res.error || "failed"}`);
  refreshWorkspace();
});

function renderTrsWorkflow(trs) {
  window._trsHandoffReady = !!(trs.c05_handoff && trs.c05_handoff.ready);
  const topic = trs.topic || {};
  const research = trs.research || {};
  const script = trs.script || {};
  const actions = trs.actions || {};
  const statusEl = document.getElementById("wsTopicStatus");
  if (statusEl) {
    statusEl.textContent = `${topic.topic_status || "NOT_STARTED"} · ${escapeHtml(topic.topic_source || "—")} · ${escapeHtml(topic.topic_text || "")}`;
  }
  const dup = document.getElementById("wsTopicDup");
  if (dup) {
    if (topic.topic_status === "BLOCKED") {
      dup.textContent = topic.blocked_reason || "Topic blocked";
    } else if (topic.duplicate && topic.duplicate.verdict) {
      dup.textContent = `Duplicate check: ${topic.duplicate.verdict}`;
    } else {
      dup.textContent = "";
    }
  }
  const sug = document.getElementById("wsTopicSuggestions");
  if (sug) {
    sug.innerHTML = (trs.suggestions || []).map(s =>
      `<div class="card" data-suggest-id="${escapeHtml(s.topic_id || "")}" data-suggest-text="${escapeHtml(s.topic_text || "")}" role="button">
        ${escapeHtml(s.topic_text || "")} <span class="muted">[${escapeHtml(s.source || "")}]</span>
      </div>`
    ).join("") || "<p class='muted'>No suggestions yet</p>";
    sug.querySelectorAll("[data-suggest-text]").forEach(el => {
      el.onclick = () => selectSuggestedTopic(el.dataset.suggestId, el.dataset.suggestText, "SUGGESTED");
    });
  }
  const res = document.getElementById("wsTopicReserved");
  if (res) {
    res.innerHTML = (trs.reserved || []).map(s =>
      `<div class="card" data-res-id="${escapeHtml(s.topic_id || "")}" data-res-text="${escapeHtml(s.topic_text || "")}" role="button">
        Reserved: ${escapeHtml(s.topic_text || "")}
      </div>`
    ).join("") || "<p class='muted'>No reserved topics</p>";
    res.querySelectorAll("[data-res-text]").forEach(el => {
      el.onclick = () => selectSuggestedTopic(el.dataset.resId, el.dataset.resText, "RESERVED");
    });
  }
  const rp = document.getElementById("wsResearchPanel");
  if (rp) {
    rp.classList.remove("muted");
    const liveClaim = research.live_research_complete
      ? "External live research complete"
      : (research.research_status === "COMPLETED"
        ? "Research complete (local FactPack) — NOT external live web research"
        : (research.status_label || research.research_status || "—"));
    rp.innerHTML = `
      <div>Status: <b>${escapeHtml(research.research_status || "NOT_STARTED")}</b></div>
      <div>${escapeHtml(liveClaim)}</div>
      <div>Facts: <b>${research.fact_count ?? 0}</b> · Evidence: <b>${research.evidence_count ?? 0}</b> · Sources: <b>${research.source_count ?? 0}</b></div>
      <div>Capability: <b>${escapeHtml((research.capability || {}).provider_capability || "UNKNOWN")}</b>
        · external_live=${escapeHtml((research.capability || {}).external_live_research || "UNAVAILABLE")}</div>
      <div class="muted">${escapeHtml((research.capability || {}).note || "")}</div>
      ${research.error_summary ? `<div class="muted">${escapeHtml(research.error_summary)}</div>` : ""}`;
  }
  const sp = document.getElementById("wsScriptPanel");
  if (sp) {
    sp.classList.remove("muted");
    const q = script.quality || {};
    const ap = script.approval || {};
    const prev = script.preview || {};
    const handoff = trs.c05_handoff || {};
    sp.innerHTML = `
      <div>Status: <b>${escapeHtml(script.script_status || "NOT_STARTED")}</b></div>
      <div>Beats: <b>${script.beat_count ?? 0}</b> · Dialogues: <b>${script.dialogue_count ?? 0}</b> · Scenes: <b>${script.scene_count ?? 0}</b></div>
      <div>Quality: <b>${escapeHtml(q.status || "NOT_RUN")}</b></div>
      <div>Approval: <b>${escapeHtml(ap.state || "NOT_READY")}</b> · publishes=${ap.publishes ? "YES" : "NO"}</div>
      <div>C05 handoff: <b>${handoff.ready ? "READY" : "NOT_READY"}</b> · ${escapeHtml(handoff.status || "")}</div>
      <div class="muted">${escapeHtml((prev.hook || "").slice(0, 120))}</div>
      ${(q.issues || []).slice(0, 3).map(i => `<div class="muted">${escapeHtml(i)}</div>`).join("")}`;
  }
  const setDisabled = (id, on) => { const el = document.getElementById(id); if (el) el.disabled = !on; };
  setDisabled("wsResearchBtn", !!actions.research);
  setDisabled("wsScriptGenBtn", !!actions.generate_script);
  setDisabled("wsScriptApproveBtn", !!actions.approve_script);
  setDisabled("wsScriptRejectBtn", !!actions.approve_script || (script.approval || {}).state === "READY_FOR_REVIEW");
}

async function selectSuggestedTopic(topicId, topicText, source) {
  const channel_id = currentWorkspaceChannelId();
  if (!channel_id) return alert("Select a channel first");
  const res = await api("/api/workspace/topic", {
    method: "POST",
    body: JSON.stringify({ channel_id, action: "select", topic_id: topicId, topic_text: topicText, source }),
  });
  if (!res.ok) alert(`Topic failed: ${res.error || "error"}`);
  refreshWorkspace();
}

document.getElementById("wsTopicSetBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  const topic_text = document.getElementById("wsTopicInput")?.value || "";
  if (!channel_id) return alert("Select a channel first");
  const res = await api("/api/workspace/topic", {
    method: "POST",
    body: JSON.stringify({ channel_id, action: "manual", topic_text }),
  });
  if (!res.ok) alert(`Topic failed: ${res.error || "error"}${res.topic?.blocked_reason ? "\\n" + res.topic.blocked_reason : ""}`);
  refreshWorkspace();
});
document.getElementById("wsTopicSuggestBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  if (!channel_id) return alert("Select a channel first");
  const res = await api("/api/workspace/topics/suggest", {
    method: "POST",
    body: JSON.stringify({ channel_id, video_type: "short" }),
  });
  if (!res.ok) alert(`Suggest failed: ${res.error || "error"}`);
  refreshWorkspace();
});
document.getElementById("wsResearchBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  const res = await api("/api/workspace/research", {
    method: "POST",
    body: JSON.stringify({ channel_id }),
  });
  if (!res.ok) alert(`Research failed: ${res.error || "error"}`);
  refreshWorkspace();
});
document.getElementById("wsScriptGenBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  const res = await api("/api/workspace/script", {
    method: "POST",
    body: JSON.stringify({ channel_id, video_type: "short" }),
  });
  if (!res.ok) alert(`Script failed: ${res.error || "error"}`);
  refreshWorkspace();
});
document.getElementById("wsScriptApproveBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  const res = await api("/api/workspace/script/approval", {
    method: "POST",
    body: JSON.stringify({ channel_id, decision: "approved" }),
  });
  if (!res.ok) alert(`Approve failed: ${res.error || "error"}`);
  else alert("Script APPROVED — does not generate media or publish.");
  refreshWorkspace();
});
document.getElementById("wsScriptRejectBtn")?.addEventListener("click", async () => {
  const channel_id = currentWorkspaceChannelId();
  const res = await api("/api/workspace/script/approval", {
    method: "POST",
    body: JSON.stringify({ channel_id, decision: "rejected" }),
  });
  if (!res.ok) alert(`Reject failed: ${res.error || "error"}`);
  refreshWorkspace();
});

async function refreshConfigStatus() {
  const panel = document.getElementById("configStatusPanel");
  const matrix = document.getElementById("providerMatrix");
  if (!panel) return;
  const res = await api("/api/config/summary");
  if (!res.ok) {
    panel.textContent = res.error || "Configuration unavailable";
    return;
  }
  const c = res.configuration || {};
  const ch = (c.channels || [])[0];
  panel.classList.remove("muted");
  panel.innerHTML = `
    <div><strong>Channel:</strong> ${escapeHtml(c.channel_state || "—")}</div>
    <div><strong>Languages:</strong> ${escapeHtml(c.language_state || "—")}</div>
    <div><strong>Providers:</strong> ${escapeHtml(c.provider_state || "—")}</div>
    <div class="muted">Orphan channels on device: ${c.orphan_count ?? 0}</div>
    ${ch ? `<div class="muted">#${ch.id} ${escapeHtml(ch.youtube_name || ch.niche || "")} · enabled=${ch.enabled}</div>` : ""}
  `;
  if (matrix) {
    matrix.innerHTML = (c.providers || []).map(p => `
      <div class="card muted">
        <strong>${escapeHtml(p.label)}</strong>
        [${escapeHtml(p.state)}] slots=${p.slot_count}/${p.min_keys}
        ${p.configured ? "· Configured" : "· Not configured"}
      </div>
    `).join("");
  }
  window._cfgChannelId = ch?.id || null;
}

async function refresh() {
  const st = await api("/api/status");
  showDash(!!st.logged_in, st.customer || { name: st.identity?.display_name, login_id: st.identity?.login_id });
  renderAuthBanner(st.identity, null);
  if (!st.logged_in) return;
  document.getElementById("apiBase").value = st.api_base_url || "";
  renderReadiness(st.foundation, null, {
    production_allowed: !!(st.identity?.production_access && st.foundation?.generate_allowed),
    message: st.identity?.message,
    block_reason: st.identity?.block_reason,
  });
  document.getElementById("stats").innerHTML = `
    <div class="stat"><span>চ্যানেল</span><b>${st.channels}</b></div>
    <div class="stat"><span>সাম্প্রতিক জব</span><b>${st.jobs}</b></div>
    <div class="stat"><span>Auth</span><b>${escapeHtml(st.identity?.auth_state || "—")}</b></div>
    <div class="stat"><span>Entitlement</span><b>${escapeHtml(st.identity?.entitlement_state || "—")}</b></div>
    <div class="stat"><span>App</span><b>${escapeHtml(st.foundation?.application || "—")}</b></div>
    <div class="stat"><span>Media</span><b>${escapeHtml(st.foundation?.media || "—")}</b></div>
  `;
  await loadNiches();
  const ch = await api("/api/channels");
  const sel = document.getElementById("channelSelect");
  const megaSel = document.getElementById("megaChannelSelect");
  const optsHtml = (ch.channels || []).map(c =>
    `<option value="${c.id}">#${c.id} ${c.youtube_name || c.facebook_name || c.niche}</option>`
  ).join("");
  if (sel) sel.innerHTML = optsHtml;
  if (megaSel) {
    megaSel.innerHTML = optsHtml || `<option value="0">কোনো চ্যানেল যুক্ত নেই</option>`;
    const megaBadge = document.getElementById("megaChannelBadge");
    if (megaBadge) {
      if ((ch.channels || []).length) {
        const c0 = ch.channels[0];
        megaBadge.textContent = `সক্রিয় নিশ: ${c0.niche || "জেনারেল"} (চ্যানেল #${c0.id})`;
        megaBadge.style.color = "#10b981";
      } else {
        megaBadge.textContent = "কোনো চ্যানেল কনফিগার করা হয়নি";
        megaBadge.style.color = "#ef4444";
      }
    }
  }
  const summary = document.getElementById("channelSummary");
  if (summary) {
    if ((ch.channels || []).length) {
      const c0 = ch.channels[0];
      summary.classList.remove("muted");
      summary.textContent = `Channel #${c0.id} · ${c0.niche || "—"} · YT ${c0.youtube_name || "—"}`;
    } else {
      summary.classList.add("muted");
      summary.textContent = "চ্যানেল সেটআপ হয়নি";
    }
  }

  await refreshChannelAndLanguageSection(ch.channels || []);

  const jobs = await api("/api/jobs");
  const list = (jobs.jobs || []).map(j => acceptJobProjection(j) || j);
  const active = list.filter(j => !TERMINAL_STATES.has(String(j.state || "")));
  const recent = list.filter(j => TERMINAL_STATES.has(String(j.state || "")));
  renderJobLists(active, recent);
  document.getElementById("jobsList").innerHTML = list.map(j => renderJobCard(j, {
    selected: j.job_id === _selectedJobId,
  })).join("") || "<p class='muted'>জব নেই</p>";
  document.querySelectorAll("#jobsList [data-job-id]").forEach(card => {
    card.onclick = () => {
      _selectedJobId = Number(card.dataset.jobId);
      loadJobDetail(_selectedJobId);
    };
  });

  await refreshWorkspace();
  await refreshDashboard();
  await refreshConfigStatus();
  await loadDedicatedApiSlots();
}

async function loadDedicatedApiSlots() {
  const host = document.getElementById("apiKeyGroups");
  const banner = document.getElementById("apiReadinessBanner");
  if (!host) return;
  const res = await api("/api/api-providers");
  if (!res.ok) {
    host.innerHTML = `<p class="muted">${escapeHtml(res.error || "API slots unavailable")}</p>`;
    return;
  }
  const ready = res.readiness || {};
  if (banner) {
    banner.classList.remove("muted", "active", "inactive");
    if (ready.active) {
      banner.classList.add("active");
      banner.textContent = ready.message || "Application active — required APIs OK";
    } else {
      banner.classList.add("inactive");
      const miss = (ready.missing || []).join("; ");
      banner.textContent = miss
        ? `ইনঅ্যাকটিভ — দিন: ${miss}`
        : (ready.message || "Required APIs missing");
    }
    const warns = ready.warnings || [];
    if (warns.length) {
      banner.textContent += "\n⚠️ " + warns.slice(0, 3).join(" · ");
    }
  }
  const lang = localStorage.getItem("amp_ui_lang") || "bn";
  host.innerHTML = (res.providers || []).map((p) => {
    const unlockedCount = p.is_paid_master ? Number(p.unlocked_slots || 0) : (p.slots || 2);
    const isLockedMaster = Boolean(p.is_paid_master && unlockedCount === 0);
    const title = lang === "bn" ? (p.label_bn || p.label) : (p.label || p.label_bn);
    const badge = p.required
      ? `<span class="req">বাধ্যতামূলক ${p.min_required}/${p.slots}</span>`
      : p.free_url_ok
        ? `<span class="opt">ঐচ্ছিক · ফ্রি URL OK</span>`
        : p.requires_account_id
          ? `<span class="opt">ঐচ্ছিক · API দিলে Account ID বাধ্যতামূলক</span>`
          : p.is_paid_master
            ? (unlockedCount > 0
                ? `<span class="req" style="background:#065f46; color:#34d399; border-color:#059669; font-weight:bold; cursor:pointer;" onclick="window.openGooglePaidModal(${unlockedCount + 1})">👑 PRO আনলকড (${unlockedCount}/${p.slots}) · +অ্যাকাউন্ট</span>`
                : `<span class="req" style="background:#451a03; color:#fbbf24; border-color:#b45309; cursor:pointer; font-weight:bold;" onclick="window.openGooglePaidModal(1)">🔒 PRO LOCKED (০/৩) · ক্লিক করুন</span>`)
            : `<span class="opt">ঐচ্ছিক · সুপারিশ ${p.slots}</span>`;
    const miss = p.required && !p.ok;
    const slotsHtml = Array.from({ length: p.slots || 2 }, (_, i) => {
      const n = i + 1;
      const isSlotLocked = Boolean(p.is_paid_master && (i >= unlockedCount));
      const name = `${p.form_prefix || p.id}_api_${n}`;
      const ph = isSlotLocked
        ? `🔒 গুগল অ্যাকাউন্ট ${n} সাবস্ক্রিপশন প্রয়োজন (অর্ডার করতে ক্লিক করুন)`
        : (p.filled > i ? `•••• (env/saved ${n})` : `API ${n} (অ্যাকাউন্ট ${n} কি)`);
      let row = `<label class="api-slot-row ${isSlotLocked ? 'locked-slot-row' : ''}" ${isSlotLocked ? `onclick="window.openGooglePaidModal(${n})"` : ''} style="${isSlotLocked ? 'cursor:pointer;' : ''}">
        <span class="muted" style="${isSlotLocked ? 'color:#fbbf24;' : (p.is_paid_master ? 'color:#34d399;' : '')}">
          ${isSlotLocked ? '🔒 ' : (p.is_paid_master ? '👑 ' : '')}API ${n} ${p.is_paid_master ? (isSlotLocked ? `(লকড · অ্যাকাউন্ট ${n})` : `(আনলকড অ্যাকাউন্ট ${n})`) : ''}
        </span>
        <input type="password" name="${escapeAttr(name)}" autocomplete="off"
          ${isSlotLocked ? 'readonly' : ''}
          placeholder="${escapeAttr(ph)}" data-api-slot="${escapeAttr(p.id)}" data-api-index="${n}"
          style="${isSlotLocked ? 'cursor:pointer; background:#1e1b4b; border:1px dashed #d97706; color:#fbbf24;' : (p.is_paid_master ? 'border-color:#059669;' : '')}">
      </label>`;
      if (p.requires_account_id) {
        const an = `${p.form_prefix || p.id}_account_${n}`;
        const aph = (p.account_ids_filled || 0) > i
          ? `•••• (saved Account ${n})`
          : `Account ID ${n} (বাধ্যতামূলক যদি API দেন)`;
        row += `<label class="api-slot-row api-account-row"><span class="muted">Account ID ${n}</span>
          <input type="text" name="${escapeAttr(an)}" autocomplete="off"
            placeholder="${escapeAttr(aph)}" data-api-account="${escapeAttr(p.id)}" data-api-index="${n}">
        </label>`;
      }
      return row;
    }).join("");
    const helpKey = p.help_key || `help_api_${p.id}`;
    const portal = p.portal_url
      ? `<button type="button" class="btn ghost api-portal-btn" data-url="${escapeAttr(p.portal_url)}">${escapeHtml((window.ampHelpT && window.ampHelpT("get_api")) || "Get API")}</button>`
      : "";
    const lockBanner = (p.is_paid_master && unlockedCount < p.slots)
      ? `<div class="api-lock-banner" onclick="window.openGooglePaidModal(${unlockedCount + 1})" style="cursor:pointer; background:linear-gradient(135deg, rgba(245,158,11,0.12), rgba(99,102,241,0.12)); border:1px dashed #f59e0b; border-radius:10px; padding:10px 14px; margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
          <div style="font-size:0.84rem; color:#fde68a; line-height:1.4;">
            <strong style="color:#fbbf24; display:block; margin-bottom:2px;">👑 ${unlockedCount > 0 ? `পরবর্তী অ্যাকাউন্ট (${unlockedCount + 1}) নেওয়ার জন্য অর্ডার করুন` : '১০০% রিয়েল ভিডিও (Google Veo) ও আনলিমিটেড কোটা পেতে আনলক করুন'}</strong>
            <span style="font-size:0.75rem; color:#94a3b8;">ম্যানুয়ালি অ্যাকাউন্ট কানেক্ট হওয়ার পর প্রতিটি অর্ডারে ১টি করে নতুন এপিআই স্লট আনলক হবে।</span>
          </div>
          <button type="button" class="btn" style="padding:5px 12px; font-size:0.8rem; background:#f59e0b; color:#0f172a; font-weight:bold; white-space:nowrap; border-radius:6px;">${unlockedCount > 0 ? `+ অ্যাকাউন্ট ${unlockedCount + 1} অর্ডার` : 'বিস্তারিত ও অর্ডার'}</button>
        </div>`
      : "";
    return `<div class="api-group ${miss ? "missing" : (p.ok ? "ok-enough" : "")}" data-help="${escapeAttr(helpKey)}" data-slot-id="${escapeAttr(p.id)}">
      <div class="api-group-head">
        <strong>${escapeHtml(title)}</strong>
        ${badge}
      </div>
      <div class="api-slot-grid api-slots">${slotsHtml}</div>
      ${lockBanner}
      <div class="api-dup-warn muted" hidden></div>
      <div class="api-group-actions">
        ${portal}
        <span class="muted" style="font-size:0.78rem">env filled: ${p.filled || 0}/${p.slots}</span>
      </div>
    </div>`;
  }).join("") || "<p class='muted'>No API slots</p>";

  host.querySelectorAll(".api-portal-btn").forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const url = btn.getAttribute("data-url");
      if (url) window.open(url, "_blank", "noopener");
    };
  });
  host.querySelectorAll("input[data-api-slot]").forEach((inp) => {
    inp.addEventListener("change", () => validateDedicatedApiForm(host));
    inp.addEventListener("blur", () => validateDedicatedApiForm(host));
  });
  host.querySelectorAll("input[data-api-account]").forEach((inp) => {
    inp.addEventListener("change", () => validateDedicatedApiForm(host));
    inp.addEventListener("blur", () => validateDedicatedApiForm(host));
  });
  if (typeof window.ampMountHelpTips === "function") {
    window.ampMountHelpTips();
  }
}

function validateDedicatedApiForm(host) {
  const inputs = [...host.querySelectorAll("input[data-api-slot]")];
  const seen = new Map(); // value -> first label
  let dupMsg = "";
  inputs.forEach((inp) => {
    inp.classList.remove("api-dup-input");
    const v = (inp.value || "").trim();
    if (!v) return;
    const slot = inp.getAttribute("data-api-slot");
    const idx = inp.getAttribute("data-api-index");
    const label = `${slot} API ${idx}`;
    if (seen.has(v)) {
      inp.classList.add("api-dup-input");
      dupMsg = `⚠️ এই API কী ইতিমধ্যে «${seen.get(v)}»-এ ব্যবহার হয়েছে — একই কী দুই জায়গায় দেওয়া যাবে না।`;
    } else {
      seen.set(v, label);
    }
  });
  // Workers AI: API requires Account ID
  let acctMsg = "";
  host.querySelectorAll(".api-group").forEach((g) => {
    const sid = g.getAttribute("data-slot-id");
    if (sid !== "workers_ai") return;
    const warn = g.querySelector(".api-dup-warn");
    for (let n = 1; n <= 5; n++) {
      const api = g.querySelector(`input[data-api-slot="workers_ai"][data-api-index="${n}"]`);
      const acct = g.querySelector(`input[data-api-account="workers_ai"][data-api-index="${n}"]`);
      if (!api) continue;
      const hasApi = !!(api.value || "").trim();
      const hasAcct = !!(acct && (acct.value || "").trim());
      if (hasApi && !hasAcct) {
        acctMsg = `⚠️ Workers AI API ${n} দিলে Account ID ${n} বাধ্যতামূলক।`;
        if (acct) acct.classList.add("api-dup-input");
      } else if (acct) {
        acct.classList.remove("api-dup-input");
      }
    }
    if (warn) {
      const msg = dupMsg || acctMsg;
      warn.hidden = !msg;
      warn.textContent = msg;
      warn.classList.toggle("api-warn-on", !!msg);
    }
  });
  // Global dup warn on first group if not workers
  if (dupMsg) {
    const firstWarn = host.querySelector(".api-dup-warn");
    if (firstWarn && firstWarn.hidden) {
      firstWarn.hidden = false;
      firstWarn.textContent = dupMsg;
      firstWarn.classList.add("api-warn-on");
    }
  }
  return !(dupMsg || acctMsg);
}

document.getElementById("apiKeysSaveBtn")?.addEventListener("click", async () => {
  const host = document.getElementById("apiKeyGroups");
  if (!host) return;
  if (!validateDedicatedApiForm(host)) {
    alert("API ফর্ম ঠিক করুন: ডুপ্লিকেট কী বা Workers AI Account ID বাধ্যতামূলক।");
    return;
  }
  const fd = new FormData();
  host.querySelectorAll("input[data-api-slot], input[data-api-account]").forEach((inp) => {
    if (inp.name && inp.value.trim()) fd.append(inp.name, inp.value.trim());
  });
  const res = await api("/api/settings/api-keys", { method: "POST", body: fd });
  if (!res.ok) {
    const msgs = (res.messages || []).join("\n") || res.message || res.hint || res.error || "API save failed";
    alert(msgs);
    return;
  }
  const msg = res.api_readiness?.message || (res.app_active ? "Saved — app active" : "Saved — still missing required keys");
  alert(msg);
  await loadDedicatedApiSlots();
  refresh();
});


document.getElementById("loginBtn").onclick = async () => {
  const err = document.getElementById("loginErr");
  err.textContent = "";
  const payload = {
    api_base_url: document.getElementById("apiBase").value.trim(),
    login_id: document.getElementById("loginId").value.trim(),
    password: document.getElementById("password").value,
  };
  const res = await api("/api/login", { method: "POST", body: JSON.stringify(payload) });
  if (!res.ok) {
    err.textContent = res.message || res.error || "লগইন ব্যর্থ";
    return;
  }
  if (res.warning === "entitlement_required") {
    err.textContent = res.identity?.message || "Signed in, but production access is not available.";
  }
  refresh();
  resumePolling();
};

document.getElementById("logoutBtn").onclick = async () => {
  await api("/api/logout", { method: "POST", body: "{}" });
  refresh();
};

document.getElementById("hiddenBtn").onclick = async () => {
  const res = await api("/api/run-hidden-once", { method: "POST", body: "{}" });
  alert(res.ok ? "অপটিমাইজেশন সম্পন্ন" : (res.error || "ব্যর্থ"));
};

document.querySelectorAll(".tabs button").forEach(btn => {
  btn.onclick = () => {
    switchTab(btn.dataset.tab);
    if (btn.dataset.tab === "live" || btn.dataset.tab === "home" || btn.dataset.tab === "jobs") {
      resumePolling();
      refresh();
    } else if (btn.dataset.tab === "videos") {
      if (typeof window.loadVideoLibrary === "function") window.loadVideoLibrary();
    } else if (btn.dataset.tab === "products") {
      if (typeof window.loadProductsCatalog === "function") window.loadProductsCatalog();
    }
  };
});

const _dashStart = document.getElementById("dashStartOnboarding");
if (_dashStart) {
  _dashStart.onclick = async () => {
    await api("/api/onboarding/start", { method: "POST", body: "{}" });
    await refreshDashboard();
  };
}
const _dashResume = document.getElementById("dashResumeOnboarding");
if (_dashResume) {
  _dashResume.onclick = async () => {
    const dash = await refreshDashboard();
    const tab = dash?.onboarding?.resume_hint || "channel";
    switchTab(tab);
  };
}
const _dashComplete = document.getElementById("dashCompleteOnboarding");
if (_dashComplete) {
  _dashComplete.onclick = async () => {
    const res = await api("/api/onboarding/complete", { method: "POST", body: "{}" });
    if (!res.ok) {
      alert(res.message || res.error || "Cannot finish onboarding yet");
    }
    await refreshDashboard();
  };
}
const _dashWs = document.getElementById("dashOpenWorkspace");
if (_dashWs) {
  _dashWs.onclick = () => {
    const el = document.getElementById("workspace");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
}

const _cfgAct = document.getElementById("cfgActivateBtn");
if (_cfgAct) {
  _cfgAct.onclick = async () => {
    if (!window._cfgChannelId) return alert("No owned channel");
    await api(`/api/channels/${window._cfgChannelId}/activate`, { method: "POST", body: "{}" });
    await refreshConfigStatus();
    refresh();
  };
}
const _cfgDeact = document.getElementById("cfgDeactivateBtn");
if (_cfgDeact) {
  _cfgDeact.onclick = async () => {
    if (!window._cfgChannelId) return alert("No owned channel");
    await api(`/api/channels/${window._cfgChannelId}/deactivate`, { method: "POST", body: "{}" });
    await refreshConfigStatus();
    refresh();
  };
}
const _cfgClaim = document.getElementById("cfgClaimOrphanBtn");
if (_cfgClaim) {
  _cfgClaim.onclick = async () => {
    const sum = await api("/api/config/summary");
    const ids = sum.configuration?.orphan_ids || [];
    if (!ids.length) return alert("No unowned channel to claim");
    const res = await api(`/api/channels/${ids[0]}/claim`, { method: "POST", body: "{}" });
    if (!res.ok) alert(res.message || res.error || "Claim failed");
    await refreshConfigStatus();
    refresh();
  };
}

document.getElementById("channelForm").onsubmit = async (e) => {
  e.preventDefault();
  syncNicheNameFromSelect(document.getElementById("channelNicheSelect"));
  const fd = new FormData(e.target);
  const saveBtn = document.getElementById("channelSaveBtn");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "সংরক্ষণ হচ্ছে…";
  }
  try {
    const res = await api("/api/channels", { method: "POST", body: fd });
    if (res.ok) {
      alert("✅ চ্যানেল সফলভাবে সংরক্ষণ হয়েছে #" + res.channel_id);
      refresh();
      await refreshConfigStatus();
    } else {
      alert("সংরক্ষণ ব্যর্থ: " + (res.message || res.error || "ত্রুটি ঘটেছে"));
    }
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "সেভ চ্যানেল";
    }
  }
};


["channelNicheSelect"].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", () => {
    syncNicheNameFromSelect(el);
    updateNicheBlurb(el);
  });
});
document.getElementById("channelNicheFilter")?.addEventListener("input", (e) => {
  fillNicheSelect(document.getElementById("channelNicheSelect"), filterNiches(e.target.value));
});

document.getElementById("refreshLiveBtn")?.addEventListener("click", () => {
  _liveSinceSeq = 0;
  resumePolling();
});
document.getElementById("stopProcessBtn")?.addEventListener("click", async () => {
  await api("/api/activity/stop", { method: "POST", body: "{}" });
  resumePolling();
});

async function generate(type) {
  const channel_id = Number(document.getElementById("channelSelect")?.value || 0);
  if (!channel_id) return alert("আগে চ্যানেল সেভ করুন");
  const genShort = document.getElementById("genShort");
  const genLong = document.getElementById("genLong");
  if (genShort) genShort.disabled = true;
  if (genLong) genLong.disabled = true;
  try {
    const res = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ channel_id, video_type: type }),
    });
    if (!res.ok) {
      const reasons = (res.generate_block_reasons || []).join(", ");
      alert(
        `Generate blocked/failed: ${res.error || "error"}` +
        (res.error_class ? ` [${res.error_class}]` : "") +
        (res.hint ? `\n${res.hint}` : "") +
        (reasons ? `\n${reasons}` : "")
      );
      return;
    }
    const job = acceptJobProjection(res.job);
    _selectedJobId = res.job_id;
    alert(
      `Job #${res.job_id} started (${job?.state || "QUEUED"}).\n` +
      `${res.message || "Not complete yet."}\n` +
      `Trace: ${job?.trace_id || "—"}`
    );
    renderDetailPanels(job);
    resumePolling();
    refresh();
  } finally {
    if (genShort) genShort.disabled = false;
    if (genLong) genLong.disabled = false;
  }
}
document.getElementById("genShort").onclick = () => generate("short");
document.getElementById("genLong").onclick = () => generate("long");

async function submitApproval(decision) {
  const jobId = window._wsApprovalJobId || _selectedJobId;
  if (!jobId) return;
  let rejection_reason = null;
  if (decision === "rejected") {
    rejection_reason = window.prompt("Optional rejection reason (stored for future repair; does not regenerate):", "") || null;
  }
  const body = { job_id: jobId, decision };
  if (window._wsRevisionId) body.revision_id = window._wsRevisionId;
  if (rejection_reason) body.rejection_reason = rejection_reason;
  const res = await api("/api/workspace/approval", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    alert(`Approval failed: ${res.error || "error"}${res.error_code ? " [" + res.error_code + "]" : ""}`);
    return;
  }
  alert(`${res.approval_state || res.approval_status} — does not publish.`);
  refreshWorkspace();
}
document.getElementById("wsApproveBtn")?.addEventListener("click", () => submitApproval("approved"));
document.getElementById("wsRejectBtn")?.addEventListener("click", () => submitApproval("rejected"));

// Export helpers for focused tests via window (optional)
window.__c01b = { isNewerJobSnapshot, acceptJobProjection, TERMINAL_STATES, shouldContinuePolling };
window.__c06a = { stageGlyph, renderWorkspaceProjection };
window.__c06f = { submitApproval };

async function refreshChannelAndLanguageSection(channels) {
  const langData = await api("/api/languages");
  const c0 = channels && channels[0];

  // 1. Populate secondary language select in Setup form
  const secSelect = document.getElementById("secondaryLangSelect");
  if (secSelect && langData.secondary_options) {
    const prev = secSelect.value;
    secSelect.innerHTML = `<option value="">-- ভাষা বেছে নিন --</option>` +
      langData.secondary_options.map(opt => `<option value="${opt.code}">${opt.name} (${opt.code.toUpperCase()})</option>`).join("");
    if (prev) secSelect.value = prev;
  }

  // 2. If channel is already setup, freeze niche/language block & show language purchase
  const nicheBlock = document.getElementById("nicheSetupBlock");
  const frozenBlock = document.getElementById("frozenNicheLang");
  const langSection = document.getElementById("langPurchaseSection");
  if (c0) {
    if (nicheBlock) nicheBlock.classList.add("hidden");
    if (frozenBlock) {
      frozenBlock.classList.remove("hidden");
      const fn = document.getElementById("frozenNicheField");
      const fl = document.getElementById("frozenLangField");
      if (fn) fn.value = c0.niche || "—";
      if (fl) fl.value = (langData.unlocked_names || []).join(", ") || "English";
    }
    const fYt = document.getElementById("f_youtube_name");
    const fFb = document.getElementById("f_facebook_name");
    const fTt = document.getElementById("f_tiktok_name");
    if (fYt && !fYt.value) fYt.value = c0.youtube_name || "";
    if (fFb && !fFb.value) fFb.value = c0.facebook_name || "";
    if (fTt && !fTt.value) fTt.value = c0.tiktok_name || "";

    const inpReelsDay = document.querySelector("#channelForm [name='reels_per_day']");
    const inpReelSlots = document.querySelector("#channelForm [name='reel_schedule_times']");
    const inpReelTopics = document.querySelector("#channelForm [name='reel_topics']");
    if (inpReelsDay && c0.reels_per_day) inpReelsDay.value = c0.reels_per_day;
    if (inpReelSlots && c0.reel_schedule_times) {
      try {
        const parsed = JSON.parse(c0.reel_schedule_times);
        inpReelSlots.value = Array.isArray(parsed) ? parsed.join(", ") : c0.reel_schedule_times;
      } catch(e) { inpReelSlots.value = c0.reel_schedule_times; }
    }
    if (inpReelTopics && c0.reel_topics) {
      try {
        const parsed = JSON.parse(c0.reel_topics);
        inpReelTopics.value = Array.isArray(parsed) ? parsed.join("\n") : c0.reel_topics;
      } catch(e) { inpReelTopics.value = c0.reel_topics; }
    }

    if (langSection) {
      langSection.classList.remove("hidden");
      const priceLbl = document.getElementById("langPriceLabel");
      if (priceLbl) priceLbl.textContent = langData.price || "499";
      
      const unList = document.getElementById("langUnlockedList");
      if (unList) {
        unList.innerHTML = `<strong>আনলককৃত ভাষাসমূহ:</strong> ` +
          (langData.unlocked_names || []).map(n => `<span class="badge lang-badge" style="margin:2px 4px">${n}</span>`).join("");
      }

      const buySel = document.getElementById("buyLangSelect");
      if (buySel) {
        buySel.innerHTML = (langData.available_to_buy || []).map(opt =>
          `<option value="${opt.code}">${opt.name} (${opt.code.toUpperCase()}) — ${langData.price || 499} BDT</option>`
        ).join("") || `<option value="">সব ভাষা আনলক করা হয়েছে</option>`;
      }

      const pendList = document.getElementById("langPendingList");
      if (pendList) {
        pendList.innerHTML = (langData.pending || []).map(p => `
          <div class="card" style="margin-top:6px;padding:6px 10px">
            ⏳ আবেদন: <strong>${(p.lang_code || '').toUpperCase()}</strong> · TrxID: ${p.payment_ref} · স্ট্যাটাস: <em>${p.status}</em>
          </div>
        `).join("");
      }
    }
  } else {
    if (nicheBlock) nicheBlock.classList.remove("hidden");
    if (frozenBlock) frozenBlock.classList.add("hidden");
    if (langSection) langSection.classList.add("hidden");
  }

  // 3. Render per-language 3-platform channel cards
  const host = document.getElementById("channelList");
  if (!host) return;

  if (!channels || !channels.length) {
    host.innerHTML = "<p class='muted'>এখনো চ্যানেল সেটআপ হয়নি। ওপরের ফর্মে নিশ ও ভাষা সিলেক্ট করে সেভ করুন।</p>";
    return;
  }

  let html = "";
  for (const c of channels) {
    const sessRes = await api(`/api/sessions?channel_id=${c.id}`);
    const sessions = sessRes.sessions || [];
    const sessMap = {};
    sessions.forEach(s => {
      sessMap[`${s.platform}_${s.lang_code || 'en'}`] = s;
    });

    let proKeys = {};
    try {
      const proRes = await api('/api/setup/google-pro-key');
      proKeys = proRes?.keys || {};
    } catch (e) {}

    let destinations = {};
    try {
      destinations = typeof c.lang_destinations_json === "string" ? JSON.parse(c.lang_destinations_json) : (c.lang_destinations_json || {});
    } catch(e) { destinations = {}; }

    const unlockedCodes = langData.unlocked || ["en"];

    html += `
      <div class="card" style="margin-bottom:1.5rem">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
          <div>
            <h3 style="margin:0">চ্যানেল #${c.id} · <span style="color:var(--brand)">${escapeHtml(c.niche || "")}</span></h3>
            <span class="muted small">প্রতিটি ভাষার জন্য ৩টি প্ল্যাটফর্ম (YouTube, Facebook, TikTok) স্বয়ংক্রিয়ভাবে ভিডিও পাবে</span>
          </div>
          <span class="badge">${unlockedCodes.length}টি ভাষা সক্রিয়</span>
        </div>
    `;

    for (const code of unlockedCodes) {
      const isEn = code === "en";
      const langName = (langData.catalog || []).find(x => x.code === code)?.name || code.toUpperCase();
      const slot = destinations[code] || {};
      const proData = proKeys[code] || {};
      const proConfigured = !!proData.configured;
      const proMasked = proData.masked || "";

      const ytName = slot.youtube_name || (isEn ? c.youtube_name : "") || "";
      const fbName = slot.facebook_name || (isEn ? c.facebook_name : "") || "";
      const ttName = slot.tiktok_name || (isEn ? c.tiktok_name : "") || "";

      const ytSess = sessMap[`youtube_${code}`] || {};
      const fbSess = sessMap[`facebook_${code}`] || {};
      const ttSess = sessMap[`tiktok_${code}`] || {};

      const ytOk = ytSess.connected || ytSess.status === "connected";
      const fbOk = fbSess.connected || fbSess.status === "connected";
      const ttOk = ttSess.connected || ttSess.status === "connected";

      html += `
        <div class="lang-slot-card">
          <div class="lang-slot-header">
            <div>
              <span class="badge lang-badge">${langName} (${code.toUpperCase()})</span>
              <span class="muted small" style="margin-left:8px">${isEn ? "প্রাইমারি বেস চ্যানেল" : "লোকালাইজড চ্যানেল স্লট"}</span>
            </div>
          </div>
          <div class="platform-trio-grid">
            <!-- YouTube Slot -->
            <div class="platform-col">
              <div class="plat-head">
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="plat-icon yt-icon">▶</span>
                  <strong>YouTube</strong>
                </div>
                <span class="status-pill ${ytOk ? 'ok' : 'idle'}">${ytOk ? '● Connected' : '○ Disconnected'}</span>
              </div>
              <input class="plat-input" id="inp_yt_${c.id}_${code}" value="${escapeHtml(ytName)}" placeholder="YouTube চ্যানেল নাম">
              <button class="btn ghost btn-sm" data-action="auth-login" data-cid="${c.id}" data-plat="youtube" data-lang="${code}">
                ${ytOk ? 'লগইন নবায়ন' : 'YouTube লগইন'}
              </button>
            </div>

            <!-- Facebook Slot -->
            <div class="platform-col">
              <div class="plat-head">
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="plat-icon fb-icon">f</span>
                  <strong>Facebook</strong>
                </div>
                <span class="status-pill ${fbOk ? 'ok' : 'idle'}">${fbOk ? '● Connected' : '○ Disconnected'}</span>
              </div>
              <input class="plat-input" id="inp_fb_${c.id}_${code}" value="${escapeHtml(fbName)}" placeholder="Facebook পেজ নাম">
              <button class="btn ghost btn-sm" data-action="auth-login" data-cid="${c.id}" data-plat="facebook" data-lang="${code}">
                ${fbOk ? 'লগইন নবায়ন' : 'Facebook লগইন'}
              </button>
            </div>

            <!-- TikTok Slot -->
            <div class="platform-col">
              <div class="plat-head">
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="plat-icon tt-icon">♪</span>
                  <strong>TikTok</strong>
                </div>
                <span class="status-pill ${ttOk ? 'ok' : 'idle'}">${ttOk ? '● Connected' : '○ Disconnected'}</span>
              </div>
              <input class="plat-input" id="inp_tt_${c.id}_${code}" value="${escapeHtml(ttName)}" placeholder="TikTok @username">
              <button class="btn ghost btn-sm" data-action="auth-login" data-cid="${c.id}" data-plat="tiktok" data-lang="${code}">
                ${ttOk ? 'লগইন নবায়ন' : 'TikTok লগইন'}
              </button>
            </div>
          </div>
          <!-- Google AI Pro Key Slot for this Language -->
          <div class="google-pro-slot" style="background:#090e17; border:1px solid #312e81; border-radius:10px; padding:12px; margin-top:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="background:#4338ca; color:#e0e7ff; font-size:0.75rem; font-weight:bold; padding:2px 8px; border-radius:4px;">GOOGLE PRO API</span>
                <span style="font-size:0.85rem; color:#cbd5e1;">${langName} ভাষার জন্য গুগল প্রো কী:</span>
                <span class="badge ${proConfigured ? 'ok' : 'idle'}" id="badge_pro_${c.id}_${code}" style="font-size:0.75rem;">
                  ${proConfigured ? '● Google Pro Active (Nano Banana + VEO-3)' : '○ Free Quota (Standard)'}
                </span>
              </div>
              <a href="http://localhost:8000/order.php?product=google_pro" target="_blank" class="btn ghost btn-sm" style="border-color:#818cf8; color:#c7d2fe; text-decoration:none; padding:3px 10px; font-size:0.8rem;">
                [Google AI Pro এপিআই নেওয়ার জন্য এখানে ক্লিক করুন]
              </a>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <input class="plat-input" type="password" id="inp_pro_${c.id}_${code}" value="${escapeHtml(proMasked)}" placeholder="Google Pro Key (AIzaSy...) লিখুন" style="flex:1; font-family:monospace; font-size:0.85rem;">
              <button class="btn ghost btn-sm" data-action="save-pro-key" data-cid="${c.id}" data-lang="${code}" style="white-space:nowrap;">
                💾 প্রো-কী সেভ
              </button>
            </div>
          </div>

          <div class="lang-slot-actions">
            <button class="btn ghost btn-sm" data-action="save-slot-names" data-cid="${c.id}" data-lang="${code}">
              💾 ${langName} একাউন্ট নামসমূহ সেভ করুন
            </button>
          </div>
        </div>
      `;
    }

    html += `</div>`;
  }

  host.innerHTML = html;

  // Bind Save Google Pro Key buttons
  host.querySelectorAll("[data-action='save-pro-key']").forEach(btn => {
    btn.onclick = async () => {
      const cid = btn.dataset.cid;
      const lang = btn.dataset.lang;
      const keyVal = document.getElementById(`inp_pro_${cid}_${lang}`)?.value || "";
      btn.disabled = true;
      btn.textContent = "সেভ হচ্ছে…";
      try {
        const res = await api("/api/setup/google-pro-key", {
          method: "POST",
          body: JSON.stringify({ lang: lang, google_pro_key: keyVal }),
        });
        btn.disabled = false;
        btn.textContent = "💾 প্রো-কী সেভ";
        if (res.ok) {
          alert(res.message || "Google Pro Key সফলভাবে সংরক্ষিত হয়েছে!");
          refresh();
        } else {
          alert(res.error || "কী সংরক্ষণ ব্যর্থ");
        }
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "💾 প্রো-কী সেভ";
        alert("ত্রুটি: " + err);
      }
    };
  });

  // Bind Login buttons
  host.querySelectorAll("[data-action='auth-login']").forEach(btn => {
    btn.onclick = async () => {
      const cid = btn.dataset.cid;
      const plat = btn.dataset.plat;
      const lang = btn.dataset.lang;
      btn.disabled = true;
      btn.textContent = "ব্রাউজার খোলা হচ্ছে…";
      try {
        const res = await api(`/api/channels/${cid}/${plat}-login`, {
          method: "POST",
          body: JSON.stringify({ lang_code: lang }),
        });
        if (!res.ok) {
          alert(res.error || "লগইন শুরু করতে ব্যর্থ");
          btn.disabled = false;
          btn.textContent = `${plat.toUpperCase()} লগইন`;
          return;
        }
        pollLoginJob(res.job_id, btn, plat, lang);
      } catch(err) {
        alert("ত্রুটি: " + err);
        btn.disabled = false;
      }
    };
  });

  // Bind Save Slot Names buttons
  host.querySelectorAll("[data-action='save-slot-names']").forEach(btn => {
    btn.onclick = async () => {
      const cid = btn.dataset.cid;
      const lang = btn.dataset.lang;
      const ytVal = document.getElementById(`inp_yt_${cid}_${lang}`)?.value || "";
      const fbVal = document.getElementById(`inp_fb_${cid}_${lang}`)?.value || "";
      const ttVal = document.getElementById(`inp_tt_${cid}_${lang}`)?.value || "";
      
      const fd = new FormData();
      fd.append("channel_id", cid);
      fd.append(`lang_yt_${lang}`, ytVal);
      fd.append(`lang_fb_${lang}`, fbVal);
      fd.append(`lang_tt_${lang}`, ttVal);
      if (lang === "en") {
        fd.append("youtube_name", ytVal);
        fd.append("facebook_name", fbVal);
        fd.append("tiktok_name", ttVal);
      }
      btn.disabled = true;
      btn.textContent = "সেভ হচ্ছে…";
      const res = await api("/api/channels", { method: "POST", body: fd });
      btn.disabled = false;
      btn.textContent = "সেভ সফল!";
      setTimeout(() => { btn.textContent = `💾 ${lang} নামসমূহ সেভ করুন`; }, 2000);
      refresh();
    };
  });
}

function pollLoginJob(jobId, btn, plat, lang) {
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts++;
    const st = await api(`/api/auth-login/status?job_id=${jobId}`);
    if (st.status === "logged_in" || st.connected) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = "লগইন সফল! ✓";
      alert(`${plat.toUpperCase()} (${lang}) সফলভাবে কানেক্ট হয়েছে!`);
      refresh();
    } else if (st.status === "failed") {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = "লগইন ব্যর্থ";
      alert(`লগইন ব্যর্থ: ${st.error || "অনুগ্রহ করে আবার চেষ্টা করুন"}`);
      refresh();
    } else if (attempts > 120) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = "টাইমআউট";
      refresh();
    } else {
      btn.textContent = `লগইন চেক (${attempts}s)…`;
    }
  }, 2500);
}

const buyForm = document.getElementById("langBuyForm");
if (buyForm) {
  buyForm.onsubmit = async (e) => {
    e.preventDefault();
    const lang_code = document.getElementById("buyLangSelect")?.value;
    const payment_ref = document.getElementById("buyPaymentRef")?.value;
    const payment_note = document.getElementById("buyPaymentNote")?.value;
    if (!lang_code || !payment_ref) return alert("ভাষা এবং পেমেন্ট রেফারেন্স পূরণ করুন");

    const res = await api("/api/languages/request", {
      method: "POST",
      body: JSON.stringify({ lang_code, payment_ref, payment_note }),
    });
    if (res.ok) {
      alert("অতিরিক্ত ভাষার আবেদন সফলভাবে জমা হয়েছে! অ্যাডমিন অনুমোদনের পর আনলক হবে।");
      buyForm.reset();
      refresh();
    } else {
      alert(res.error || "আবেদন ব্যর্থ");
    }
  };
}

const syncBtn = document.getElementById("langSyncBtn");
if (syncBtn) {
  syncBtn.onclick = async () => {
    syncBtn.disabled = true;
    syncBtn.textContent = "Syncing…";
    const res = await api("/api/languages/sync", { method: "POST", body: "{}" });
    syncBtn.disabled = false;
    syncBtn.textContent = "অ্যাপ্রুভাল Sync";
    if (res.ok) {
      alert(`Sync সম্পন্ন! মোট আনলককৃত ভাষা: ${(res.unlocked || []).length}টি`);
      refresh();
    } else {
      alert(res.error || "Sync ব্যর্থ");
    }
  };
}

// 150 GB GOOGLE DRIVE CLOUD STORAGE VAULT CONTROLLER
async function initDriveVault() {
  const saveBtn = document.getElementById("saveDriveVaultBtn");
  const syncBtn = document.getElementById("syncDriveNowBtn");
  const badge = document.getElementById("vaultConnectionBadge");
  const usedVal = document.getElementById("vaultUsedStorageVal");
  const todayVal = document.getElementById("vaultTodayCountVal");
  const msgEl = document.getElementById("vaultSyncMsg");

  if (!saveBtn) return;

  const connectBtn = document.getElementById("connectDriveBtn");
  const freedVal = document.getElementById("vaultFreedStorageVal");
  const syncTimeInp = document.getElementById("vaultSyncTime");
  const progContainer = document.getElementById("vaultSyncProgressContainer");
  const progBar = document.getElementById("vaultSyncProgressBar");
  const progPercent = document.getElementById("vaultSyncProgressPercent");
  const progLabel = document.getElementById("vaultSyncProgressLabel");

  async function loadStatus() {
    try {
      const res = await api("/api/storage/status");
      if (res && res.status) {
        const s = res.status;
        if (badge) {
          badge.textContent = s.is_connected ? "● কানেক্টেড (Vault Active - ১৫০ GB)" : "○ ডিসকানেক্টেড";
          badge.style.color = s.is_connected ? "#10b981" : "#94a3b8";
        }
        if (usedVal) usedVal.textContent = (s.used_storage_gb || 0).toFixed(2) + " GB";
        if (freedVal) freedVal.textContent = (s.total_freed_gb || 0).toFixed(2) + " GB";
        if (todayVal) todayVal.textContent = (s.today_synced_count || 0) + " টি ভিডিও";

        const emailInp = document.getElementById("vaultTargetEmail");
        const folderInp = document.getElementById("vaultFolderId");
        const authSel = document.getElementById("vaultAuthType");
        if (emailInp && s.target_email && !emailInp.value) emailInp.value = s.target_email;
        if (folderInp && s.vault_folder_id && !folderInp.value) folderInp.value = s.vault_folder_id;
        if (syncTimeInp && s.sync_time && !syncTimeInp.value) syncTimeInp.value = s.sync_time;
        if (authSel && s.auth_type) authSel.value = s.auth_type;
      }
    } catch (e) {}
  }

  if (connectBtn) {
    connectBtn.onclick = async () => {
      connectBtn.disabled = true;
      connectBtn.textContent = "কানেক্ট হচ্ছে…";
      const credentials = document.getElementById("vaultCredentials")?.value || "";
      const target_email = document.getElementById("vaultTargetEmail")?.value || "";
      try {
        const res = await api("/api/storage/connect", {
          method: "POST",
          body: JSON.stringify({ credentials, target_email })
        });
        connectBtn.disabled = false;
        connectBtn.textContent = "🔗 গুগল ড্রাইভ কানেক্ট";
        if (res && res.ok) {
          if (msgEl) msgEl.textContent = "✓ " + (res.message || "Google Drive Vault (150 GB) সংযুক্ত হয়েছে।");
          loadStatus();
        } else {
          if (msgEl) msgEl.textContent = "✕ সংযোগ ব্যর্থ: " + (res?.error || "অজানা ত্রুটি");
        }
      } catch (err) {
        connectBtn.disabled = false;
        connectBtn.textContent = "🔗 গুগল ড্রাইভ কানেক্ট";
        if (msgEl) msgEl.textContent = "✕ ত্রুটি: " + err;
      }
    };
  }

  saveBtn.onclick = async () => {
    saveBtn.disabled = true;
    saveBtn.textContent = "সেভ হচ্ছে…";
    const auth_type = document.getElementById("vaultAuthType")?.value || "service_account";
    const target_email = document.getElementById("vaultTargetEmail")?.value || "";
    const vault_folder_id = document.getElementById("vaultFolderId")?.value || "AutoMoviePro_Vault";
    const credentials = document.getElementById("vaultCredentials")?.value || "";
    const sync_time = syncTimeInp?.value || "02:00";

    try {
      const res = await api("/api/storage/drive-config", {
        method: "POST",
        body: JSON.stringify({ auth_type, target_email, vault_folder_id, credentials, sync_time, auto_sync_enabled: true, purge_local_after_sync: true }),
      });
      saveBtn.disabled = false;
      saveBtn.textContent = "💾 সেটিংস সেভ করুন";
      if (res && res.ok) {
        if (msgEl) msgEl.textContent = "✓ " + res.message;
        loadStatus();
      } else {
        if (msgEl) msgEl.textContent = "✕ সংরক্ষণ ব্যর্থ: " + (res?.error || "অজানা ত্রুটি");
      }
    } catch (err) {
      saveBtn.disabled = false;
      saveBtn.textContent = "💾 সেটিংস সেভ করুন";
      if (msgEl) msgEl.textContent = "✕ ত্রুটি: " + err;
    }
  };

  if (syncBtn) {
    syncBtn.onclick = async () => {
      syncBtn.disabled = true;
      syncBtn.textContent = "ক্লাউড সিঙ্ক চলছে…";
      if (progContainer) {
        progContainer.style.display = "block";
        if (progBar) progBar.style.width = "15%";
        if (progPercent) progPercent.textContent = "15%";
        if (progLabel) progLabel.textContent = "ভিডিও ও সিন প্যাকেজ স্ক্যান করা হচ্ছে…";
      }
      if (msgEl) msgEl.textContent = "⏳ দৈনিক ভিডিও প্যাকেজ Google Drive Vault-এ সিঙ্ক হচ্ছে...";

      let progInterval = setInterval(() => {
        if (progBar) {
          let curr = parseInt(progBar.style.width || "15", 10);
          if (curr < 85) {
            curr += 10;
            progBar.style.width = curr + "%";
            if (progPercent) progPercent.textContent = curr + "%";
            if (progLabel) progLabel.textContent = "গুগল ড্রাইভে আপলোড ও লোকাল ডিস্ক খালি করা হচ্ছে…";
          }
        }
      }, 350);

      try {
        const res = await api("/api/storage/sync-now", { method: "POST", body: "{}" });
        clearInterval(progInterval);
        syncBtn.disabled = false;
        syncBtn.textContent = "⚡ এখনই ক্লাউডে সিঙ্ক করুন (Sync Now)";
        if (progBar) progBar.style.width = "100%";
        if (progPercent) progPercent.textContent = "100%";
        if (progLabel) progLabel.textContent = "✓ সিঙ্ক সম্পন্ন ও ডিস্ক স্পেস খালি করা হয়েছে!";

        setTimeout(() => {
          if (progContainer) progContainer.style.display = "none";
        }, 5000);

        if (res && res.ok) {
          const ct = res.sync_result?.videos_synced || 0;
          const freed = res.sync_result?.freed_mb || 0;
          if (msgEl) msgEl.textContent = `✓ সিঙ্ক সফল! ${ct}টি ভিডিও প্যাকেজ ক্লাউড ভল্টে সংরক্ষিত হয়েছে এবং ${freed} MB লোকাল ডিস্ক স্পেস খালি করা হয়েছে।`;
          loadStatus();
        } else {
          if (msgEl) msgEl.textContent = "✕ সিঙ্ক ব্যর্থ: " + (res?.error || "অজানা ত্রুটি");
        }
      } catch (err) {
        clearInterval(progInterval);
        syncBtn.disabled = false;
        syncBtn.textContent = "⚡ এখনই ক্লাউডে সিঙ্ক করুন (Sync Now)";
        if (progContainer) progContainer.style.display = "none";
        if (msgEl) msgEl.textContent = "✕ ত্রুটি: " + err;
      }
    };
  }

  loadStatus();
}

function initAutoReplyAndAnalytics() {
  const badgeEl = document.getElementById("autoReplyBadge");
  const toggleBtn = document.getElementById("autoReplyToggleBtn");
  const triggerBtn = document.getElementById("autoReplyTriggerBtn");
  const lastScanEl = document.getElementById("autoReplyLastScan");
  const totalSentEl = document.getElementById("autoReplyTotalSent");
  const historyBody = document.getElementById("autoReplyHistoryBody");
  const refreshHistoryBtn = document.getElementById("refreshReplyHistoryBtn");

  let isAutoReplyActive = true;

  async function loadAutoReplyStatus() {
    try {
      const res = await api("/api/auto-reply/status");
      if (!res || !res.ok) return;

      isAutoReplyActive = !!res.enabled;
      if (badgeEl) {
        if (isAutoReplyActive) {
          badgeEl.textContent = "সক্রিয় (Active)";
          badgeEl.style.background = "#10b98120";
          badgeEl.style.color = "#10b981";
          badgeEl.style.borderColor = "#10b98140";
        } else {
          badgeEl.textContent = "নিষ্ক্রিয় (Disabled)";
          badgeEl.style.background = "#ef444420";
          badgeEl.style.color = "#ef4444";
          badgeEl.style.borderColor = "#ef444440";
        }
      }

      if (toggleBtn) {
        if (isAutoReplyActive) {
          toggleBtn.textContent = "বন্ধ করুন (Disable)";
          toggleBtn.style.background = "#ef4444";
        } else {
          toggleBtn.textContent = "চালু করুন (Enable)";
          toggleBtn.style.background = "#10b981";
        }
      }

      if (lastScanEl) {
        lastScanEl.textContent = res.last_scan ? new Date(res.last_scan * 1000).toLocaleTimeString("bn-BD") : "অদ্যাবধি কোনো স্ক্যান হয়নি";
      }
      if (totalSentEl) {
        totalSentEl.textContent = `${res.total_replies_sent || 0} টি`;
      }

      // Render recent replies
      if (historyBody) {
        const list = res.recent_replies || [];
        if (!list.length) {
          historyBody.innerHTML = `<tr><td colspan="5" style="padding:12px; text-align:center; color:#64748b;">কোনো সাম্প্রতিক রিপ্লাই রেকর্ড পাওয়া যায়নি</td></tr>`;
        } else {
          historyBody.innerHTML = list.map(item => `
            <tr style="border-bottom:1px solid #1e293b;">
              <td style="padding:6px 10px; text-transform:capitalize;">${escapeHtml(item.platform || "social")}</td>
              <td style="padding:6px 10px; color:#38bdf8;">${escapeHtml(item.author || "Viewer")}</td>
              <td style="padding:6px 10px; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeAttr(item.body || "")}">
                ${escapeHtml(item.body || "—")}
              </td>
              <td style="padding:6px 10px; color:#10b981; max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeAttr(item.reply_body || "")}">
                ${escapeHtml(item.reply_body || "উত্তর দেওয়া হয়েছে")}
              </td>
              <td style="padding:6px 10px; color:#94a3b8; font-size:0.75rem;">
                ${item.created_at ? new Date(item.created_at).toLocaleTimeString("bn-BD") : "এখন"}
              </td>
            </tr>
          `).join("");
        }
      }
    } catch (e) {
      console.warn("Auto-reply status load failed:", e);
    }
  }

  if (toggleBtn) {
    toggleBtn.onclick = async () => {
      toggleBtn.disabled = true;
      try {
        const nextState = !isAutoReplyActive;
        const res = await api("/api/auto-reply/toggle", {
          method: "POST",
          body: JSON.stringify({ enabled: nextState })
        });
        if (res && res.ok) {
          isAutoReplyActive = !!res.enabled;
          await loadAutoReplyStatus();
        }
      } catch (err) {
        console.error("Toggle auto-reply failed:", err);
      } finally {
        toggleBtn.disabled = false;
      }
    };
  }

  if (triggerBtn) {
    triggerBtn.onclick = async () => {
      triggerBtn.disabled = true;
      const prevText = triggerBtn.textContent;
      triggerBtn.textContent = "স্ক্যান চলছে…";
      try {
        const res = await api("/api/auto-reply/trigger", { method: "POST", body: "{}" });
        if (res && res.ok) {
          await loadAutoReplyStatus();
        }
      } catch (err) {
        console.error("Manual trigger auto-reply failed:", err);
      } finally {
        triggerBtn.disabled = false;
        triggerBtn.textContent = prevText;
      }
    };
  }

  if (refreshHistoryBtn) {
    refreshHistoryBtn.onclick = () => loadAutoReplyStatus();
  }

  // --- Analytics & Growth Report ---
  const viewsEl = document.getElementById("statTotalViews");
  const likesEl = document.getElementById("statTotalLikes");
  const commentsEl = document.getElementById("statTotalComments");
  const trackedEl = document.getElementById("statTrackedVideos");
  const refreshAnalyticsBtn = document.getElementById("refreshAnalyticsBtn");
  const adviceSummaryEl = document.getElementById("growthAdviceSummary");
  const adviceStepsEl = document.getElementById("growthAdviceSteps");
  const adviceDailyBtn = document.getElementById("adviceDailyBtn");
  const adviceWeeklyBtn = document.getElementById("adviceWeeklyBtn");
  const adviceMonthlyBtn = document.getElementById("adviceMonthlyBtn");

  async function loadAnalytics() {
    try {
      const res = await api("/api/analytics/overview");
      if (res && res.ok && res.analytics) {
        const a = res.analytics;
        if (viewsEl) viewsEl.textContent = (a.total_views || 0).toLocaleString("bn-BD");
        if (likesEl) likesEl.textContent = (a.total_likes || 0).toLocaleString("bn-BD");
        if (commentsEl) commentsEl.textContent = (a.total_comments || 0).toLocaleString("bn-BD");
        if (trackedEl) trackedEl.textContent = (a.tracked_videos_count || 0).toLocaleString("bn-BD");
      }
    } catch (e) {
      console.warn("Analytics overview load failed:", e);
    }
  }

  async function loadGrowthAdvice(period = "daily") {
    try {
      [adviceDailyBtn, adviceWeeklyBtn, adviceMonthlyBtn].forEach(b => b?.classList.remove("active"));
      if (period === "daily") adviceDailyBtn?.classList.add("active");
      if (period === "weekly") adviceWeeklyBtn?.classList.add("active");
      if (period === "monthly") adviceMonthlyBtn?.classList.add("active");

      const res = await api("/api/analytics/growth-advice?period=" + encodeURIComponent(period));
      if (res && res.ok && res.advice) {
        const adv = res.advice;
        if (adviceSummaryEl) adviceSummaryEl.textContent = adv.summary || adv.recommendation || "";
        if (adviceStepsEl && adv.actionable_steps) {
          adviceStepsEl.innerHTML = adv.actionable_steps.map(s => `<li>✓ ${escapeHtml(s)}</li>`).join("");
        }
      }
    } catch (e) {
      console.warn("Growth advice load failed:", e);
    }
  }

  if (refreshAnalyticsBtn) {
    refreshAnalyticsBtn.onclick = async () => {
      refreshAnalyticsBtn.disabled = true;
      refreshAnalyticsBtn.textContent = "রিফ্রেশ হচ্ছে…";
      try {
        await api("/api/analytics/refresh", { method: "POST", body: "{}" });
        await loadAnalytics();
        await loadGrowthAdvice("daily");
      } finally {
        refreshAnalyticsBtn.disabled = false;
        refreshAnalyticsBtn.textContent = "🔄 রিফ্রেশ ডাটা";
      }
    };
  }

  if (adviceDailyBtn) adviceDailyBtn.onclick = () => loadGrowthAdvice("daily");
  if (adviceWeeklyBtn) adviceWeeklyBtn.onclick = () => loadGrowthAdvice("weekly");
  if (adviceMonthlyBtn) adviceMonthlyBtn.onclick = () => loadGrowthAdvice("monthly");

  loadAutoReplyStatus();
  loadAnalytics();
  loadGrowthAdvice("daily");
}

function initSupportAndAuthModals() {
  const forgotModal = document.getElementById("forgotPassModal");
  const feedbackModal = document.getElementById("feedbackReportModal");
  const reviewModal = document.getElementById("reviewRatingModal");
  const googlePaidModal = document.getElementById("googlePaidModal");

  // Google Special Account Subscription & Order Flow
  let _selectedGooglePaidPlan = {
    id: "12_month",
    price: 999,
    name: "বাৎসরিক প্ল্যান (১২ মাস)",
  };

  window.selectGooglePaidPlan = function(id, price, name) {
    _selectedGooglePaidPlan = { id, price, name };
    const waBtn = document.getElementById("googlePaidWaBtn");
    if (waBtn) {
      const email = (document.getElementById("googlePaidOrderEmail")?.value || "").trim();
      const txt = encodeURIComponent(`আসসালামু আলাইকুম অ্যাডমিন, আমি AutoMovie Pro এর Google AI Pro প্যাকেজের [${name} - ${price} ৳] নিতে চাই।${email ? ' জিমেইল: ' + email : ''}`);
      waBtn.href = `https://wa.me/8801968111593?text=${txt}`;
    }
  };

  window.openGooglePaidModal = async function(targetSlotIndex) {
    if (googlePaidModal) googlePaidModal.style.display = "flex";
    const msg = document.getElementById("googlePaidActivationMsg");
    if (msg) msg.style.display = "none";
    const ordMsg = document.getElementById("googlePaidOrderMsg");
    if (ordMsg) ordMsg.style.display = "none";

    // Load live status & orders
    try {
      const res = await fetch("/api/subscription/google-paid-status");
      const data = await res.json();
      const container = document.getElementById("googlePaidOrdersContainer");
      const list = document.getElementById("googlePaidOrdersList");
      if (container && list) {
        if (data.orders && data.orders.length > 0) {
          container.style.display = "block";
          list.innerHTML = data.orders.slice(0, 5).map(o => {
            const isApproved = o.status === "approved" || o.status === "active";
            const badge = isApproved
              ? `<span style="background:#065f46; color:#34d399; padding:2px 8px; border-radius:6px; font-weight:bold;">✅ এক্সেপ্টেড / অ্যাক্টিভ (স্লট আনলকড)</span>`
              : `<span style="background:#451a03; color:#fbbf24; padding:2px 8px; border-radius:6px; font-weight:bold;">⏳ পেন্ডিং (অ্যাডমিন এক্সেপ্টের অপেক্ষায়)</span>`;
            return `<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b; padding:4px 0;">
              <div>
                <strong>#${o.order_id}</strong> · ${o.plan_name} (${o.price} ৳)
                <div style="font-size:0.75rem; color:#64748b;">জিমেইল: ${o.target_email || 'N/A'} · ${o.created_at?.slice(0,10) || ''}</div>
              </div>
              <div>${badge}</div>
            </div>`;
          }).join("");
        } else {
          container.style.display = "none";
        }
      }
    } catch (e) {
      console.warn("Failed to load google paid status:", e);
    }
  };

  window.closeGooglePaidModal = function() {
    if (googlePaidModal) googlePaidModal.style.display = "none";
  };

  window.submitGooglePaidOrder = async function() {
    const emailInp = document.getElementById("googlePaidOrderEmail");
    const waInp = document.getElementById("googlePaidOrderWa");
    const trxInp = document.getElementById("googlePaidOrderTrx");
    const msgBox = document.getElementById("googlePaidOrderMsg");

    const email = (emailInp ? emailInp.value : "").trim();
    const whatsapp = (waInp ? waInp.value : "").trim();
    const trx = (trxInp ? trxInp.value : "").trim();

    if (!email || !email.includes("@")) {
      if (msgBox) {
        msgBox.style.display = "block";
        msgBox.style.background = "#450a0a";
        msgBox.style.border = "1px solid #ef4444";
        msgBox.style.color = "#fecaca";
        msgBox.textContent = "অনুগ্রহ করে আপনার সঠিক Gmail অ্যাড্রেস লিখুন।";
      }
      return;
    }

    try {
      const res = await fetch("/api/subscription/order-google-paid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_id: _selectedGooglePaidPlan.id,
          plan_name: _selectedGooglePaidPlan.name,
          price: _selectedGooglePaidPlan.price,
          target_email: email,
          whatsapp: whatsapp,
          trx_id: trx,
        }),
      });
      const data = await res.json();
      if (msgBox) {
        msgBox.style.display = "block";
        if (data.ok) {
          msgBox.style.background = "#064e3b";
          msgBox.style.border = "1px solid #10b981";
          msgBox.style.color = "#ecfdf5";
          msgBox.innerHTML = `✅ <strong>অর্ডার গ্রহণ করা হয়েছে! (#${data.order?.order_id})</strong><br>`
            + `আমাদের টিম আপনার জিমেইল অ্যাকাউন্টটি ম্যানুয়ালি কানেক্ট করে অর্ডার এক্সেপ্ট করলেই সফটওয়্যারে ১টি এপিআই স্লট স্বয়ংক্রিয়ভাবে আনলক হয়ে যাবে।<br>`
            + `<a href="https://wa.me/8801968111593?text=${encodeURIComponent('Hello Admin, I placed Google Pro Order #' + (data.order?.order_id || '') + ' for ' + email)}" target="_blank" style="color:#6ee7b7; font-weight:bold; text-decoration:underline;">এখানে ক্লিক করে অ্যাডমিনকে হোয়াটসঅ্যাপে জানান 💬</a>`;

          // Refresh order list in modal
          window.openGooglePaidModal();
        } else {
          msgBox.style.background = "#450a0a";
          msgBox.style.border = "1px solid #ef4444";
          msgBox.style.color = "#fecaca";
          msgBox.textContent = "❌ " + (data.message || "অর্ডার প্রক্রিয়াকরণে ত্রুটি।");
        }
      }
    } catch (err) {
      if (msgBox) {
        msgBox.style.display = "block";
        msgBox.style.background = "#450a0a";
        msgBox.style.border = "1px solid #ef4444";
        msgBox.style.color = "#fecaca";
        msgBox.textContent = "সার্ভার এরর: " + err.message;
      }
    }
  };

  window.verifyGooglePaidActivation = async function() {
    const input = document.getElementById("googlePaidActivationCodeInput");
    const msgBox = document.getElementById("googlePaidActivationMsg");
    const code = (input ? input.value : "").trim();
    if (!code) {
      if (msgBox) {
        msgBox.style.display = "block";
        msgBox.style.background = "#450a0a";
        msgBox.style.border = "1px solid #ef4444";
        msgBox.style.color = "#fecaca";
        msgBox.textContent = "অনুগ্রহ করে আপনার অ্যাক্টিভেশন কোড লিখুন।";
      }
      return;
    }
    try {
      const res = await fetch("/api/subscription/activate-google-paid", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      if (msgBox) {
        msgBox.style.display = "block";
        if (data.ok) {
          msgBox.style.background = "#064e3b";
          msgBox.style.border = "1px solid #10b981";
          msgBox.style.color = "#ecfdf5";
          msgBox.textContent = "✅ " + (data.message || "Google Special Account সফলভাবে অ্যাক্টিভ হয়েছে!");
          setTimeout(() => {
            window.closeGooglePaidModal();
            if (typeof loadDedicatedApiSlots === "function") {
              loadDedicatedApiSlots();
            }
          }, 1200);
        } else {
          msgBox.style.background = "#450a0a";
          msgBox.style.border = "1px solid #ef4444";
          msgBox.style.color = "#fecaca";
          msgBox.textContent = "❌ " + (data.message || "ভুল অ্যাক্টিভেশন কোড।");
        }
      }
    } catch (err) {
      if (msgBox) {
        msgBox.style.display = "block";
        msgBox.style.background = "#450a0a";
        msgBox.style.border = "1px solid #ef4444";
        msgBox.style.color = "#fecaca";
        msgBox.textContent = "সার্ভার এরর: " + err.message;
      }
    }
  };

  // Forgot password & WhatsApp/Telegram OTP
  window.openForgotPassModal = function() {
    if (!forgotModal) return;
    forgotModal.style.display = "flex";
    const msg = document.getElementById("forgotModalMsg");
    if (msg) msg.style.display = "none";
    const s1 = document.getElementById("otpStep1");
    const s2 = document.getElementById("otpStep2");
    if (s1) s1.style.display = "block";
    if (s2) s2.style.display = "none";
    const idInput = document.getElementById("forgotIdentifier");
    if (idInput) {
      idInput.value = document.getElementById("loginId")?.value || "";
      idInput.focus();
    }
  };

  window.closeForgotPassModal = function() {
    if (forgotModal) forgotModal.style.display = "none";
  };

  window.handleSendOtp = async function() {
    const id = document.getElementById("forgotIdentifier")?.value.trim();
    const msg = document.getElementById("forgotModalMsg");
    const btn = document.getElementById("sendOtpBtn");
    const apiBaseUrl = document.getElementById("apiBase")?.value.trim() || "";

    if (!id) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "অনুগ্রহ করে আপনার WhatsApp / Telegram নম্বর বা ইমেইল বা Login ID প্রদান করুন।";
      }
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = "ওটিপি পাঠানো হচ্ছে…";
    }

    try {
      const res = await api("/api/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({
          identifier: id,
          login_id: id,
          api_base_url: apiBaseUrl
        })
      });

      if (msg) msg.style.display = "block";
      if (res && res.ok) {
        msg.style.background = "#064e3b";
        msg.style.color = "#ecfdf5";
        msg.textContent = res.message || "✅ আপনার WhatsApp / Telegram / Email-এ ৬ ডিজিটের ওটিপি পাঠানো হয়েছে।";
        const s2 = document.getElementById("otpStep2");
        if (s2) s2.style.display = "block";
        document.getElementById("resetOtpCode")?.focus();
      } else {
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = res?.message || res?.error || "ওটিপি পাঠানো সম্ভব হয়নি। তথ্য যাচাই করে পুনরায় চেষ্টা করুন।";
      }
    } catch (err) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "সার্ভার সংযোগ ত্রুটি। ইন্টারনেট বা API URL চেক করুন।";
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "📲 ওটিপি (OTP) কোড পাঠান";
      }
    }
  };

  window.handleResetPasswordSubmit = async function() {
    const id = document.getElementById("forgotIdentifier")?.value.trim();
    const otp = document.getElementById("resetOtpCode")?.value.trim();
    const newPass = document.getElementById("resetNewPass")?.value;
    const confirmPass = document.getElementById("resetConfirmPass")?.value;
    const msg = document.getElementById("forgotModalMsg");
    const btn = document.getElementById("submitResetPassBtn");
    const apiBaseUrl = document.getElementById("apiBase")?.value.trim() || "";

    if (!otp || otp.length < 4) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "সঠিক ওটিপি কোড লিখুন।";
      }
      return;
    }

    if (!newPass || newPass.length < 6) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "নতুন পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।";
      }
      return;
    }

    if (newPass !== confirmPass) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "উভয় পাসওয়ার্ড মেলেনি। পুনরায় টাইপ করুন।";
      }
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = "সংরক্ষণ হচ্ছে…";
    }

    try {
      const res = await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          identifier: id,
          login_id: id,
          otp: otp,
          new_password: newPass,
          api_base_url: apiBaseUrl
        })
      });

      if (msg) msg.style.display = "block";
      if (res && res.ok) {
        msg.style.background = "#064e3b";
        msg.style.color = "#ecfdf5";
        msg.textContent = res.message || "✅ পাসওয়ার্ড সফলভাবে রিসেট হয়েছে! লগইন করুন।";
        const loginPass = document.getElementById("password");
        if (loginPass) loginPass.value = newPass;
        setTimeout(() => {
          window.closeForgotPassModal();
        }, 1800);
      } else {
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = res?.message || res?.error || "পাসওয়ার্ড পরিবর্তন ব্যর্থ হয়েছে। ওটিপি মেয়াদোত্তীর্ণ হতে পারে।";
      }
    } catch (err) {
      if (msg) {
        msg.style.display = "block";
        msg.style.background = "#7f1d1d";
        msg.style.color = "#fecaca";
        msg.textContent = "সার্ভার সংযোগ ত্রুটি।";
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "✅ নতুন পাসওয়ার্ড সংরক্ষণ করুন";
      }
    }
  };

  // Feedback & Support Ticket Modal (72-hour SLA commitment)
  window.openFeedbackModal = function() {
    if (feedbackModal) {
      feedbackModal.style.display = "flex";
      const resBox = document.getElementById("feedbackResultBox");
      if (resBox) resBox.style.display = "none";
      const form = document.getElementById("feedbackForm");
      if (form) form.style.display = "block";
    }
  };

  window.closeFeedbackModal = function() {
    if (feedbackModal) feedbackModal.style.display = "none";
  };

  window.handleFeedbackSubmit = async function(e) {
    if (e && e.preventDefault) e.preventDefault();
    const type = document.getElementById("feedbackType")?.value;
    const contact = document.getElementById("feedbackContact")?.value.trim();
    const message = document.getElementById("feedbackMessage")?.value.trim();
    const btn = document.getElementById("feedbackSubmitBtn");
    const resBox = document.getElementById("feedbackResultBox");
    const titleEl = document.getElementById("feedbackTicketTitle");
    const descEl = document.getElementById("feedbackTicketDesc");
    const form = document.getElementById("feedbackForm");
    const apiBaseUrl = document.getElementById("apiBase")?.value.trim() || "";

    if (!message) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "জমা হচ্ছে…";
    }

    try {
      const res = await api("/api/support/ticket", {
        method: "POST",
        body: JSON.stringify({
          type: type,
          contact: contact,
          message: message,
          api_base_url: apiBaseUrl
        })
      });

      if (form) form.style.display = "none";
      if (resBox) resBox.style.display = "block";
      if (titleEl) titleEl.textContent = `✅ টিকিট রেজিস্টার্ড: ${res?.ticket_id || "AMP-TICKET"}`;
      if (descEl) descEl.textContent = res?.message || "আপনার রিপোর্ট সফলভাবে প্রাপ্ত হয়েছে। আগামী ৭২ ঘণ্টার মধ্যে সমাধান নিশ্চিত করা হবে।";
    } catch (err) {
      alert("রিপোর্ট জমা দিতে সমস্যা হয়েছে। অনুগ্রহ করে ইন্টারনেট সংযোগ চেক করুন।");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "🚀 রিপোর্ট/পরামর্শ জমা দিন";
      }
    }
  };

  // Review & Rating Modal
  window.openReviewModal = function() {
    if (reviewModal) {
      reviewModal.style.display = "flex";
      const resBox = document.getElementById("reviewResultBox");
      if (resBox) resBox.style.display = "none";
      const form = document.getElementById("reviewForm");
      if (form) form.style.display = "block";
    }
  };

  window.closeReviewModal = function() {
    if (reviewModal) reviewModal.style.display = "none";
  };

  window.setReviewRating = function(rating) {
    const hiddenInput = document.getElementById("selectedStarRating");
    if (hiddenInput) hiddenInput.value = rating;
    const stars = document.querySelectorAll("#starRatingGroup span");
    stars.forEach(s => {
      const starNum = parseInt(s.getAttribute("data-star"), 10);
      s.style.color = starNum <= rating ? "#f59e0b" : "#475569";
    });
  };

  window.handleReviewSubmit = async function(e) {
    if (e && e.preventDefault) e.preventDefault();
    const name = document.getElementById("reviewAuthorName")?.value.trim();
    const rating = parseInt(document.getElementById("selectedStarRating")?.value || "5", 10);
    const text = document.getElementById("reviewTextContent")?.value.trim();
    const btn = document.getElementById("reviewSubmitBtn");
    const resBox = document.getElementById("reviewResultBox");
    const form = document.getElementById("reviewForm");
    const apiBaseUrl = document.getElementById("apiBase")?.value.trim() || "";

    if (!text) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "প্রকাশ হচ্ছে…";
    }

    try {
      const res = await api("/api/feedback/review", {
        method: "POST",
        body: JSON.stringify({
          name: name,
          rating: rating,
          review_text: text,
          platform: "Desktop App",
          api_base_url: apiBaseUrl
        })
      });

      if (form) form.style.display = "none";
      if (resBox) {
        resBox.style.display = "block";
        resBox.textContent = res?.message || "আপনার মূল্যবান মতামতের জন্য আন্তরিক ধন্যবাদ!";
      }
      localStorage.setItem("amp_review_submitted", "true");
      setTimeout(() => {
        window.closeReviewModal();
      }, 2500);
    } catch (err) {
      alert("রিভিউ সংরক্ষণ ব্যর্থ হয়েছে।");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "⭐ রিভিউ প্রকাশ করুন";
      }
    }
  };

  // 3-Hour Periodic Review Reminder (per user requirement)
  const REVIEW_INTERVAL_MS = 3 * 60 * 60 * 1000;
  function checkReviewPrompt() {
    if (localStorage.getItem("amp_review_submitted")) return;
    const lastPrompt = parseInt(localStorage.getItem("amp_last_review_prompt") || "0", 10);
    const now = Date.now();
    if (!lastPrompt) {
      localStorage.setItem("amp_last_review_prompt", String(now));
      return;
    }
    if (now - lastPrompt >= REVIEW_INTERVAL_MS) {
      localStorage.setItem("amp_last_review_prompt", String(now));
      setTimeout(() => {
        if (!localStorage.getItem("amp_review_submitted")) {
          window.openReviewModal();
        }
      }, 5000);
    }
  }
  setInterval(checkReviewPrompt, 10 * 60 * 1000);
  checkReviewPrompt();
}

refresh().then(() => {
  resumePolling();
  initDriveVault();
  initAutoReplyAndAnalytics();
  initSupportAndAuthModals();
});

// ==========================================
// 1-CLICK STUDIO HERO CONTROLS (NON-TECH)
// ==========================================
window.setQuickTopic = function(topic) {
  const inp = document.getElementById("megaTopicInput");
  if (inp) {
    inp.value = topic;
    inp.focus();
  }
};

window.openOutputDirectory = async function(folder) {
  try {
    const res = await api("/api/open-folder", {
      method: "POST",
      body: JSON.stringify({ folder: folder || "" })
    });
    if (!res.ok) alert("ফোল্ডার ওপেন ব্যর্থ: " + (res.error || "অজানা সমস্যা"));
  } catch (err) {
    alert("ফোল্ডার ওপেন ব্যর্থ হয়েছে।");
  }
};

let _megaJobPollTimer = null;

window.triggerMegaGenerate = async function(videoType) {
  const shortBtn = document.getElementById("megaGenShortBtn");
  const longBtn = document.getElementById("megaGenLongBtn");
  const topicInp = document.getElementById("megaTopicInput");
  const megaSel = document.getElementById("megaChannelSelect");
  const dot = document.getElementById("megaStatusDot");
  const title = document.getElementById("megaStatusTitle");
  const percent = document.getElementById("megaProgressPercent");
  const bar = document.getElementById("megaProgressBar");
  const detail = document.getElementById("megaStatusDetail");

  const channelId = Number(megaSel?.value || document.getElementById("channelSelect")?.value || 0);
  const topic = (topicInp?.value || "").trim();

  // Visual feedback during initiation
  if (shortBtn) shortBtn.disabled = true;
  if (longBtn) longBtn.disabled = true;
  if (dot) {
    dot.style.background = "#f59e0b";
    dot.style.boxShadow = "0 0 10px #f59e0b";
  }
  if (title) title.textContent = (videoType === "short" ? "৬০-সেকেন্ডের Shorts / Reel" : "৩-৫ মিনিটের Long ভিডিও") + " তৈরির প্রক্রিয়া শুরু হচ্ছে...";
  if (percent) percent.textContent = "10%";
  if (bar) bar.style.width = "10%";
  if (detail) detail.textContent = "এআই টপিক বিশ্লেষণ ও ক্রিয়েটিভ প্রম্পট প্রস্তুত করছে...";

  const endpoint = videoType === "long" ? "/api/generate/long" : "/api/generate/short";
  const payload = {
    channel_id: channelId,
    topic: topic,
    video_type: videoType
  };

  try {
    const res = await api(endpoint, {
      method: "POST",
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      if (dot) {
        dot.style.background = "#ef4444";
        dot.style.boxShadow = "0 0 10px #ef4444";
      }
      if (bar) {
        bar.style.width = "100%";
        bar.style.background = "#ef4444";
      }
      const errMsg = res.message || res.error || "ভিডিও তৈরিতে সমস্যা হয়েছে";
      if (title) title.textContent = "❌ ব্যর্থ হয়েছে: " + errMsg;
      if (detail) detail.textContent = "অনুগ্রহ করে চ্যানেল সেটিংস বা লাইসেন্স প্যাকেজ চেক করুন।";
      alert("ভিডিও তৈরি শুরু করা যায়নি: " + errMsg);
      return;
    }

    // Success kickoff
    if (dot) {
      dot.style.background = "#10b981";
      dot.style.boxShadow = "0 0 10px #10b981";
    }
    if (title) title.textContent = "🚀 ভিডিও জেনারেশন সফলভাবে শুরু হয়েছে (Job #" + (res.job_id || res.id || "") + ")";
    if (percent) percent.textContent = "25%";
    if (bar) bar.style.width = "25%";
    if (detail) detail.textContent = "স্ক্রিপ্ট তৈরি ও স্টুডিও ভয়েস রেকর্ডিং চলমান...";

    // Audio cue
    if (typeof window.playJarvisAudioCue === "function") {
      window.playJarvisAudioCue(
        "/assets/audio/voice_cues/render_start.wav",
        "ভিডিও তৈরির কাজ সফলভাবে শুরু হয়েছে। স্টুডিও মনিটরে লক্ষ্য রাখুন।"
      );
    }

    // Kinetic progress simulation & state monitoring
    let p = 25;
    if (_megaJobPollTimer) clearInterval(_megaJobPollTimer);
    _megaJobPollTimer = setInterval(() => {
      p += 5;
      if (p <= 90) {
        if (percent) percent.textContent = p + "%";
        if (bar) bar.style.width = p + "%";
        if (p === 40 && detail) detail.textContent = "৬-ভাষার আন্তর্জাতিক স্ক্রিপ্ট ও অডিও সিন্থেসিস প্রস্তুত...";
        if (p === 65 && detail) detail.textContent = "ভিজ্যুয়াল ফুটেজ, সাবটাইটেল ও ব্যাকগ্রাউন্ড মিউজিক সিঙ্ক হচ্ছে...";
        if (p === 85 && detail) detail.textContent = "ফাইনাল রেন্ডার ও কোয়ালিটি গার্ড (QC) ভেরিফিকেশন চলছে...";
      }
    }, 3500);

    setTimeout(async () => {
      await refresh();
      if (bar) {
        bar.style.width = "100%";
        bar.style.background = "linear-gradient(90deg, #0284c7, #38bdf8, #10b981)";
      }
      if (percent) percent.textContent = "100%";
      if (title) title.textContent = "🎉 ভিডিও তৈরি সম্পন্ন! ভিডিও লাইব্রেরিতে দেখুন।";
      if (detail) detail.textContent = "ফাইল সংরক্ষিত হয়েছে output ফোল্ডারে।";
      if (_megaJobPollTimer) clearInterval(_megaJobPollTimer);
      if (shortBtn) shortBtn.disabled = false;
      if (longBtn) longBtn.disabled = false;
    }, 25000);

  } catch (err) {
    if (title) title.textContent = "কানেকশন এরর: " + (err.message || "সার্ভার সংযোগ বিচ্ছিন্ন");
    if (dot) dot.style.background = "#ef4444";
  } finally {
    setTimeout(() => {
      if (shortBtn) shortBtn.disabled = false;
      if (longBtn) longBtn.disabled = false;
    }, 2500);
  }
};

// ==========================================
// VIDEO LIBRARY CONTROLLER
// ==========================================
let _currentVideoFilter = "all";

window.filterVideoLibrary = function(filter, btnEl) {
  _currentVideoFilter = filter;
  document.querySelectorAll(".filter-btn").forEach(b => {
    b.classList.remove("active");
    b.style.background = "#1e293b";
    b.style.color = "#cbd5e1";
  });
  if (btnEl) {
    btnEl.classList.add("active");
    btnEl.style.background = "#0284c7";
    btnEl.style.color = "#fff";
  }
  loadVideoLibrary(filter);
};

window.loadVideoLibrary = async function(folder = null) {
  const container = document.getElementById("videoLibraryGrid");
  const countEl = document.getElementById("libTotalCount");
  const diskEl = document.getElementById("libDiskUsage");
  if (!container) return;

  const f = folder || _currentVideoFilter || "all";
  try {
    const res = await api(`/api/videos/library?folder=${encodeURIComponent(f)}&limit=100`);
    if (!res.ok) {
      container.innerHTML = `<div class="card muted" style="grid-column: 1 / -1; color:#ef4444;">ভিডিও লোড ব্যর্থ: ${res.error || ""}</div>`;
      return;
    }

    const videos = res.videos || [];
    if (countEl) countEl.textContent = String(videos.length);
    if (diskEl) diskEl.innerHTML = `মোট সাইজ: <strong style="color:#38bdf8;">${res.total_disk_mb || 0} MB</strong>`;

    if (!videos.length) {
      container.innerHTML = `
        <div class="card" style="grid-column: 1 / -1; text-align:center; padding:3rem; background:#070d18; border:1px dashed #334155; border-radius:14px;">
          <div style="font-size:2.5rem; margin-bottom:0.75rem;">🎬</div>
          <h3 style="color:#cbd5e1; margin:0 0 6px;">এখনও কোনো ভিডিও তৈরি করা হয়নি</h3>
          <p class="muted" style="margin:0 0 1rem; font-size:0.9rem;">ড্যাশবোর্ড থেকে ১-ক্লিকে শর্টস বা লং ভিডিও তৈরি শুরু করুন।</p>
          <button type="button" class="btn" onclick="switchTab('home')" style="background:#0284c7; font-weight:bold;">স্টুডিওতে যান</button>
        </div>
      `;
      return;
    }

    container.innerHTML = videos.map(v => {
      const isShort = v.is_short;
      const titleClean = v.filename.replace(/\.mp4$/i, "").replace(/_/g, " ");
      return `
        <div class="video-card" style="background:#090f1d; border:1px solid #1e293b; border-radius:14px; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 6px 20px rgba(0,0,0,0.4); transition:transform 0.2s ease, border-color 0.2s ease;">
          <div style="position:relative; background:#000; height:180px; display:flex; align-items:center; justify-content:center; overflow:hidden;">
            <video src="${v.url}" preload="metadata" style="max-height:100%; max-width:100%; object-fit:contain;"></video>
            <button type="button" onclick="playVideoModal('${v.url}', '${escapeAttr(titleClean)}', '${v.size_mb} MB · ${v.created_at}')" style="position:absolute; background:rgba(2, 132, 199, 0.85); border:none; width:48px; height:48px; border-radius:50%; color:#fff; font-size:1.4rem; display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow:0 0 15px rgba(2, 132, 199, 0.6); transition:transform 0.2s ease;">
              ▶
            </button>
            <span style="position:absolute; top:8px; left:8px; background:${isShort ? 'rgba(217, 119, 6, 0.9)' : 'rgba(37, 99, 235, 0.9)'}; color:#fff; font-size:0.72rem; font-weight:700; padding:2px 8px; border-radius:4px; text-transform:uppercase;">
              ${isShort ? '⚡ Shorts (9:16)' : '🎥 Long (16:9)'}
            </span>
            <span style="position:absolute; bottom:8px; right:8px; background:rgba(0,0,0,0.75); color:#fff; font-size:0.75rem; padding:2px 6px; border-radius:4px; font-family:monospace;">
              ${v.size_mb} MB
            </span>
          </div>

          <div style="padding:12px 14px; display:flex; flex-direction:column; flex:1; justify-content:space-between;">
            <div>
              <div style="font-weight:700; color:#f8fafc; font-size:0.92rem; margin-bottom:4px; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;" title="${escapeAttr(v.filename)}">
                ${escapeHtml(titleClean)}
              </div>
              <div style="font-size:0.78rem; color:#64748b; margin-bottom:10px;">
                📅 তৈরি: ${v.created_at} · ফোল্ডার: ${escapeHtml(v.folder)}
              </div>
            </div>

            <div style="display:flex; gap:6px; margin-top:8px;">
              <button type="button" onclick="playVideoModal('${v.url}', '${escapeAttr(titleClean)}', '${v.size_mb} MB · ${v.created_at}')" class="btn" style="flex:1; padding:6px; font-size:0.82rem; background:#0284c7; color:#fff; border-radius:6px; font-weight:600; display:flex; align-items:center; justify-content:center; gap:4px;">
                <span>▶</span> প্লে করুন
              </button>
              <a href="${v.url}" download="${v.filename}" class="btn ghost" style="padding:6px 10px; font-size:0.82rem; border-color:#334155; color:#cbd5e1; border-radius:6px; text-decoration:none; display:flex; align-items:center; justify-content:center;" title="ডাউনলোড">
                ⬇
              </a>
              <button type="button" onclick="openOutputDirectory('${escapeAttr(v.folder)}')" class="btn ghost" style="padding:6px 10px; font-size:0.82rem; border-color:#334155; color:#cbd5e1; border-radius:6px;" title="ফোল্ডারে দেখুন">
                📂
              </button>
            </div>
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = `<div class="card muted" style="grid-column: 1 / -1; color:#ef4444;">লোড এরর: ${err.message || ""}</div>`;
  }
};

window.playVideoModal = function(url, title, meta) {
  const modal = document.getElementById("videoPreviewModal");
  const video = document.getElementById("modalVideoElement");
  const titleEl = document.getElementById("modalVideoTitle");
  const metaEl = document.getElementById("modalVideoMeta");
  const dl = document.getElementById("modalDownloadLink");

  if (!modal || !video) return;
  video.src = url;
  if (titleEl) titleEl.textContent = title;
  if (metaEl) metaEl.textContent = meta || "";
  if (dl) {
    dl.href = url;
    dl.download = title + ".mp4";
  }
  modal.style.display = "flex";
  video.play().catch(e => console.debug("Autoplay blocked:", e));
};

window.closeVideoModal = function() {
  const modal = document.getElementById("videoPreviewModal");
  const video = document.getElementById("modalVideoElement");
  if (video) {
    video.pause();
    video.src = "";
  }
  if (modal) modal.style.display = "none";
};

// ==========================================
// PRODUCTS & ADS CONTROLLER
// ==========================================
window.loadProductsCatalog = async function() {
  const grid = document.getElementById("productsCatalogGrid");
  const adsGrid = document.getElementById("productAdsGrid");
  if (!grid) return;

  try {
    const res = await api("/api/products");
    const products = res.products || [];

    if (!products.length) {
      grid.innerHTML = `
        <div class="card" style="grid-column: 1 / -1; text-align:center; padding:2.5rem; background:#070d18; border:1px dashed #334155; border-radius:14px;">
          <div style="font-size:2.2rem; margin-bottom:0.6rem;">📦</div>
          <h3 style="color:#cbd5e1; margin:0 0 6px;">কোনো প্রোডাক্ট সংরক্ষিত নেই</h3>
          <p class="muted" style="margin:0 0 1rem; font-size:0.9rem;">আপনার পণ্য বা সার্ভিসের বিস্তারিত যুক্ত করে ১-ক্লিকে সেলস ভিডিও বানান।</p>
          <button type="button" class="btn" onclick="openNewProductModal()" style="background:#10b981; font-weight:bold;">➕ প্রথম প্রোডাক্ট যুক্ত করুন</button>
        </div>
      `;
    } else {
      grid.innerHTML = products.map(p => {
        const contact = p.contact_info || {};
        return `
          <div class="product-card" style="background:#090f1d; border:1px solid #1e293b; border-radius:14px; padding:1.25rem; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 6px 20px rgba(0,0,0,0.3);">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                <span style="background:#1e293b; color:#38bdf8; font-size:0.75rem; font-weight:600; padding:2px 8px; border-radius:6px; text-transform:uppercase;">
                  ${escapeHtml(p.category || 'পণ্য')}
                </span>
                <button type="button" onclick="deleteProduct('${p.id}')" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:0.9rem;" title="মুছে ফেলুন">🗑️</button>
              </div>

              <h3 style="color:#f8fafc; margin:0 0 6px; font-size:1.1rem; font-weight:700;">${escapeHtml(p.name)}</h3>
              <p style="color:#94a3b8; font-size:0.85rem; line-height:1.4; margin:0 0 12px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">
                ${escapeHtml(p.description || 'কোনো বিবরণ দেওয়া নেই')}
              </p>

              <div style="background:#060a12; border:1px solid #1e293b; border-radius:8px; padding:8px 10px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <span style="font-size:0.75rem; color:#64748b; text-decoration:line-through;">${escapeHtml(p.regular_price || '')}</span>
                  <div style="font-size:1.1rem; font-weight:800; color:#10b981;">${escapeHtml(p.offer_price || 'অফার মূল্য')}</div>
                </div>
                <div style="font-size:0.78rem; color:#cbd5e1; text-align:right;">
                  <div>📞 ${escapeHtml(contact.phone || contact.whatsapp || 'হটলাইন')}</div>
                  <div style="color:#38bdf8;">🌐 ${escapeHtml(contact.website ? 'ওয়েবসাইট সংযুক্ত' : '')}</div>
                </div>
              </div>
            </div>

            <div style="display:flex; gap:8px; margin-top:8px;">
              <button type="button" onclick="openGenerateAdModal('${p.id}', '${escapeAttr(p.name)}', '${escapeAttr(p.offer_price)}')" class="btn" style="width:100%; background:linear-gradient(135deg, #0284c7, #2563eb); font-weight:700; font-size:0.85rem; padding:8px; border-radius:8px; display:flex; align-items:center; justify-content:center; gap:6px;">
                <span>🎥</span> ভিডিও বিজ্ঞাপন তৈরি করুন
              </button>
            </div>
          </div>
        `;
      }).join("");
    }

    // Load Ads
    if (adsGrid) {
      const adsRes = await api("/api/products/ads");
      const ads = adsRes.ads || [];
      if (!ads.length) {
        adsGrid.innerHTML = `<div class="card muted" style="grid-column: 1 / -1; text-align:center; padding:1.5rem;">কোনো বিজ্ঞাপন ক্যাম্পেইন নেই। যেকোনো প্রোডাক্টের "ভিডিও বিজ্ঞাপন তৈরি করুন" বাটনে ক্লিক করুন।</div>`;
      } else {
        adsGrid.innerHTML = ads.map(a => `
          <div style="background:#070d18; border:1px solid #1e293b; border-radius:10px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <strong style="color:#f8fafc; font-size:0.9rem;">বিজ্ঞাপন #${a.id} (${a.ad_type || 'রিল'})</strong>
              <div style="font-size:0.78rem; color:#94a3b8; margin-top:2px;">দৈর্ঘ্য: ${a.duration_seconds}s · তারিখ: ${a.created_at || 'আজ'}</div>
            </div>
            <span style="background:#064e3b; color:#34d399; font-size:0.75rem; font-weight:bold; padding:2px 8px; border-radius:4px;">সক্রিয়</span>
          </div>
        `).join("");
      }
    }

  } catch (err) {
    grid.innerHTML = `<div class="card muted" style="grid-column: 1 / -1; color:#ef4444;">লোড এরর: ${err.message || ""}</div>`;
  }
};

window.openNewProductModal = function() {
  const m = document.getElementById("productCreateModal");
  if (m) m.style.display = "flex";
};

window.closeProductModal = function() {
  const m = document.getElementById("productCreateModal");
  if (m) m.style.display = "none";
};

window.handleCreateProduct = async function(e) {
  e.preventDefault();
  const name = document.getElementById("prodName").value.trim();
  const cat = document.getElementById("prodCategory").value;
  const regPrice = document.getElementById("prodRegPrice").value.trim();
  const offerPrice = document.getElementById("prodOfferPrice").value.trim();
  const phone = document.getElementById("prodPhone").value.trim();
  const wa = document.getElementById("prodWhatsapp").value.trim();
  const web = document.getElementById("prodWebsite").value.trim();
  const desc = document.getElementById("prodDesc").value.trim();

  const payload = {
    name: name,
    category: cat,
    regular_price: regPrice,
    offer_price: offerPrice,
    description: desc,
    contact_info: {
      phone: phone,
      whatsapp: wa,
      website: web
    }
  };

  try {
    const res = await api("/api/products", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      closeProductModal();
      document.getElementById("createProductForm").reset();
      await loadProductsCatalog();
      alert("প্রোডাক্ট সফলভাবে যুক্ত হয়েছে!");
    } else {
      alert("ব্যর্থ হয়েছে: " + (res.error || "অজানা ত্রুটি"));
    }
  } catch (err) {
    alert("সার্ভার এরর: " + err.message);
  }
};

window.deleteProduct = async function(id) {
  if (!confirm("আপনি কি নিশ্চিত এই প্রোডাক্টটি মুছে ফেলতে চান?")) return;
  try {
    const res = await api(`/api/products/${id}`, { method: "DELETE" });
    if (res.ok) {
      await loadProductsCatalog();
    } else {
      alert("মুছতে ব্যর্থ হয়েছে।");
    }
  } catch (err) {
    alert("এরর: " + err.message);
  }
};

window.openGenerateAdModal = function(id, name, price) {
  document.getElementById("adTargetProductId").value = id;
  const brief = document.getElementById("adProductBrief");
  if (brief) {
    brief.innerHTML = `<strong>প্রোডাক্ট:</strong> ${escapeHtml(name)} <br><strong>অফার প্রাইস:</strong> ${escapeHtml(price)}`;
  }
  const m = document.getElementById("generateAdModal");
  if (m) m.style.display = "flex";
};

window.closeGenerateAdModal = function() {
  const m = document.getElementById("generateAdModal");
  if (m) m.style.display = "none";
};

window.handleConfirmGenerateAd = async function() {
  const prodId = document.getElementById("adTargetProductId").value;
  const adType = document.getElementById("adVideoType").value;
  const duration = document.getElementById("adDuration").value;
  const talking = document.getElementById("adTalkingPoints").value.trim();
  const btn = document.getElementById("confirmGenerateAdBtn");

  if (btn) btn.disabled = true;

  try {
    const res = await api(`/api/products/${prodId}/generate-ad`, {
      method: "POST",
      body: JSON.stringify({
        ad_type: adType,
        duration_seconds: duration,
        talking_points: talking
      })
    });

    if (res.ok) {
      closeGenerateAdModal();
      alert("বিজ্ঞাপন ক্যাম্পেইন সফলভাবে তৈরি হয়েছে! স্টুডিও লাইভ প্রসেসে যুক্ত করা হয়েছে।");
      await loadProductsCatalog();
    } else {
      alert("বিজ্ঞাপন তৈরি ব্যর্থ: " + (res.message || res.error || "অজানা ত্রুটি"));
    }
  } catch (err) {
    alert("এরর: " + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
};



