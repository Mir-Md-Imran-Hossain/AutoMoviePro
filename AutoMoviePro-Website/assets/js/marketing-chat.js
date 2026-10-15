/**
 * AutoMovie Pro — Live Human Multi-Agent Support & Marketing Chat
 * Features rotating human consultant team (Ayesha, Nirob, Tania),
 * natural conversational sales guidance, coupon validation, and WhatsApp handoff.
 */
(function () {
  const site = window.AMP_SITE || { price: 3999, addon: 499, features: [], waLink: "" };
  const history = [];
  let activeCoupon = null;

  // ---------------------------------------------------------------------------
  // Multi-Agent Rotating Support Team
  // ---------------------------------------------------------------------------
  const SUPPORT_TEAM = [
    {
      id: "ayesha",
      name: "আয়েশা (Ayesha)",
      role: "সিনিয়র কাস্টমার কনসালট্যান্ট",
      avatar: "/assets/img/agents/ayesha.png",
      greet: "আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে আয়েশা বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?"
    },
    {
      id: "nirob",
      name: "নীরব (Nirob)",
      role: "টেকনিক্যাল ও প্রোডাক্ট স্পেশালিস্ট",
      avatar: "/assets/img/agents/nirob.png",
      greet: "আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে নীরব বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?"
    },
    {
      id: "tania",
      name: "তানিয়া (Tania)",
      role: "অনবোর্ডিং ও লাইসেন্স ম্যানেজার",
      avatar: "/assets/img/agents/tania.png",
      greet: "আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে তানিয়া বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?"
    }
  ];

  const STORAGE_KEY_HISTORY = "amp_chat_history";
  const STORAGE_KEY_VID = "amp_visitor_id";
  const STORAGE_KEY_AGENT = "amp_assigned_agent_id";
  const MAX_SAVED_HISTORY = 40;

  // ---------------------------------------------------------------------------
  // Web Audio API Sound Effects Engine (Zero Latency, Pure Native Synthesis)
  // ---------------------------------------------------------------------------
  const AmpChatAudio = (function () {
    let ctx = null;
    let isMuted = false;

    try {
      isMuted = localStorage.getItem("amp_chat_muted") === "1";
    } catch (e) {}

    function getAudioContext() {
      if (!ctx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          ctx = new AudioCtx();
        }
      }
      if (ctx && ctx.state === "suspended") {
        ctx.resume().catch(function () {});
      }
      return ctx;
    }

    // Auto-unlock on first user interaction to satisfy browser autoplay policy
    function unlock() {
      const c = getAudioContext();
      if (c && c.state === "suspended") {
        c.resume().catch(function () {});
      }
    }
    ["click", "keydown", "touchstart"].forEach(function (evt) {
      window.addEventListener(evt, unlock, { once: true, passive: true });
    });

    function toggleMute() {
      isMuted = !isMuted;
      try {
        localStorage.setItem("amp_chat_muted", isMuted ? "1" : "0");
      } catch (e) {}
      updateSoundButtonUI();
      return isMuted;
    }

    function updateSoundButtonUI() {
      const btn = document.getElementById("ampChatSoundToggle");
      if (btn) {
        btn.textContent = isMuted ? "🔇" : "🔊";
        btn.title = isMuted ? "সাউন্ড আনমিউট করুন" : "সাউন্ড মিউট করুন";
        if (isMuted) {
          btn.classList.add("is-muted");
        } else {
          btn.classList.remove("is-muted");
        }
      }
    }

    // 1. Message Sent: Crisp upward ramp (420Hz -> 840Hz, 120ms)
    function playSent() {
      if (isMuted) return;
      const c = getAudioContext();
      if (!c) return;
      try {
        const now = c.currentTime;
        const osc = c.createOscillator();
        const gain = c.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(420, now);
        osc.frequency.exponentialRampToValueAtTime(840, now + 0.10);

        gain.gain.setValueAtTime(0.14, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

        osc.connect(gain);
        gain.connect(c.destination);

        osc.start(now);
        osc.stop(now + 0.13);
      } catch (e) {}
    }

    // 2. Typing Started: Soft pleasant double-tap bubble sound (320Hz & 380Hz, 80ms)
    function playTypingStart() {
      if (isMuted) return;
      const c = getAudioContext();
      if (!c) return;
      try {
        const now = c.currentTime;

        const osc1 = c.createOscillator();
        const gain1 = c.createGain();
        osc1.type = "sine";
        osc1.frequency.setValueAtTime(320, now);
        osc1.frequency.exponentialRampToValueAtTime(220, now + 0.04);
        gain1.gain.setValueAtTime(0.09, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
        osc1.connect(gain1);
        gain1.connect(c.destination);
        osc1.start(now);
        osc1.stop(now + 0.05);

        const osc2 = c.createOscillator();
        const gain2 = c.createGain();
        osc2.type = "sine";
        osc2.frequency.setValueAtTime(380, now + 0.06);
        osc2.frequency.exponentialRampToValueAtTime(260, now + 0.10);
        gain2.gain.setValueAtTime(0.09, now + 0.06);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
        osc2.connect(gain2);
        gain2.connect(c.destination);
        osc2.start(now + 0.06);
        osc2.stop(now + 0.12);
      } catch (e) {}
    }

    // 3. Message Received: Crystal two-tone notification chime (E5 659Hz -> A5 880Hz, 320ms)
    function playReceived() {
      if (isMuted) return;
      const c = getAudioContext();
      if (!c) return;
      try {
        const now = c.currentTime;

        // Note 1: E5 (659Hz)
        const osc1 = c.createOscillator();
        const gain1 = c.createGain();
        osc1.type = "sine";
        osc1.frequency.setValueAtTime(659.25, now);
        gain1.gain.setValueAtTime(0.15, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
        osc1.connect(gain1);
        gain1.connect(c.destination);
        osc1.start(now);
        osc1.stop(now + 0.23);

        // Note 2: A5 (880Hz)
        const osc2 = c.createOscillator();
        const gain2 = c.createGain();
        osc2.type = "sine";
        osc2.frequency.setValueAtTime(880, now + 0.08);
        gain2.gain.setValueAtTime(0.18, now + 0.08);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
        osc2.connect(gain2);
        gain2.connect(c.destination);
        osc2.start(now + 0.08);
        osc2.stop(now + 0.33);
      } catch (e) {}
    }

    // 4. Agent Handshake / Connected: Harmonic triad flourish (C5 -> E5 -> G5, 300ms)
    function playConnected() {
      if (isMuted) return;
      const c = getAudioContext();
      if (!c) return;
      try {
        const now = c.currentTime;
        const notes = [523.25, 659.25, 783.99]; // C5, E5, G5
        notes.forEach(function (freq, i) {
          const osc = c.createOscillator();
          const gain = c.createGain();
          const noteStart = now + (i * 0.08);

          osc.type = "triangle";
          osc.frequency.setValueAtTime(freq, noteStart);

          gain.gain.setValueAtTime(0.12, noteStart);
          gain.gain.exponentialRampToValueAtTime(0.001, noteStart + 0.22);

          osc.connect(gain);
          gain.connect(c.destination);

          osc.start(noteStart);
          osc.stop(noteStart + 0.24);
        });
      } catch (e) {}
    }

    return {
      unlock: unlock,
      isMuted: function () { return isMuted; },
      toggleMute: toggleMute,
      updateSoundButtonUI: updateSoundButtonUI,
      playSent: playSent,
      playTypingStart: playTypingStart,
      playReceived: playReceived,
      playConnected: playConnected
    };
  })();

  function getVisitorId() {
    let vid = "";
    try {
      vid = localStorage.getItem(STORAGE_KEY_VID) || "";
    } catch (e) {}

    if (!vid) {
      const match = document.cookie.match(/(?:^|;\s*)amp_vid=([^;]+)/);
      if (match && match[1]) {
        vid = decodeURIComponent(match[1]);
      }
    }

    if (!vid) {
      vid = "vid_" + Date.now().toString(36) + "_" + Math.random().toString(36).substring(2, 10);
    }

    try {
      localStorage.setItem(STORAGE_KEY_VID, vid);
      const d = new Date();
      d.setTime(d.getTime() + (365 * 24 * 60 * 60 * 1000));
      document.cookie = "amp_vid=" + encodeURIComponent(vid) + "; expires=" + d.toUTCString() + "; path=/; SameSite=Lax";
    } catch (e) {}

    return vid;
  }

  function getAssignedAgent() {
    let savedId = null;
    try {
      savedId = localStorage.getItem(STORAGE_KEY_AGENT);
    } catch (e) {}

    let agent = SUPPORT_TEAM.find(function (a) { return a.id === savedId; });
    if (!agent) {
      // Pick random agent from team for fresh visitor
      const idx = Math.floor(Math.random() * SUPPORT_TEAM.length);
      agent = SUPPORT_TEAM[idx];
      try {
        localStorage.setItem(STORAGE_KEY_AGENT, agent.id);
      } catch (e) {}
    }
    return agent;
  }

  function setAssignedAgent(agentId) {
    if (!agentId) return null;
    const agent = SUPPORT_TEAM.find(function (a) { return a.id === agentId; });
    if (agent) {
      try {
        localStorage.setItem(STORAGE_KEY_AGENT, agent.id);
      } catch (e) {}
      applyAgentToUI(agent);
      return agent;
    }
    return null;
  }

  function loadSavedChatHistory() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_HISTORY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function appendToSavedHistory(item) {
    try {
      const list = loadSavedChatHistory();
      list.push(item);
      const trimmed = list.slice(-MAX_SAVED_HISTORY);
      localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(trimmed));
    } catch (e) {}
  }

  function clearSavedHistory() {
    try {
      localStorage.removeItem(STORAGE_KEY_HISTORY);
    } catch (e) {}
  }

  let hasRenderedSavedHistory = false;
  function renderSavedHistoryToUI() {
    if (hasRenderedSavedHistory) return;
    const log = document.getElementById("ampChatLog");
    if (!log) return;

    const saved = loadSavedChatHistory();
    if (!saved || saved.length === 0) return;

    saved.forEach(function (item) {
      const div = document.createElement("div");
      div.className = "amp-chat-bubble amp-chat-" + (item.role === "user" ? "user" : "bot") + " amp-chat-saved-msg";

      if (item.role === "user") {
        const textSpan = document.createElement("div");
        textSpan.textContent = item.content || item.text || "";
        div.appendChild(textSpan);

        const statusMeta = document.createElement("div");
        statusMeta.className = "msg-status-meta";
        statusMeta.innerHTML = '<span class="status-tick is-seen">✓✓</span> <span class="status-label">' + esc(item.time || "সংরক্ষিত") + '</span>';
        div.appendChild(statusMeta);
      } else {
        const textSpan = document.createElement("div");
        textSpan.textContent = item.content || item.text || "";
        div.appendChild(textSpan);

        if (item.checkoutUrl) {
          const ctaWrap = document.createElement("div");
          ctaWrap.style.cssText = "margin-top:10px; padding-top:8px; border-top:1px dashed rgba(255,255,255,0.2);";
          const ctaBtn = document.createElement("a");
          ctaBtn.href = item.checkoutUrl;
          ctaBtn.className = "amp-chat-cta-btn";
          ctaBtn.style.cssText = "display:inline-flex; align-items:center; gap:6px; background:linear-gradient(135deg, #10b981, #059669); color:#ffffff; font-weight:700; font-size:0.85rem; padding:8px 14px; border-radius:6px; text-decoration:none; box-shadow:0 2px 8px rgba(16,185,129,0.3);";
          ctaBtn.innerHTML = "🎟️ ৳৫০০ নগদ ছাড়ে এখনই অর্ডার করুন →";
          ctaWrap.appendChild(ctaBtn);
          div.appendChild(ctaWrap);
        }

        if (item.time) {
          const timeTag = document.createElement("span");
          timeTag.className = "amp-chat-time-tag";
          timeTag.textContent = item.time;
          div.appendChild(timeTag);
        }
      }

      log.appendChild(div);
      history.push({ role: item.role === "user" ? "user" : "assistant", content: item.content || item.text || "" });
    });

    const divider = document.createElement("div");
    divider.className = "amp-chat-divider";
    divider.innerHTML = "<span>🕒 পূর্ববর্তী কথোপকথন সংরক্ষিত</span>";
    log.appendChild(divider);
    log.scrollTop = log.scrollHeight;

    hasRenderedSavedHistory = true;
  }

  function applyAgentToUI(agent) {
    const avatarImgs = [
      document.getElementById("ampLauncherAvatar"),
      document.getElementById("ampChoiceAvatar"),
      document.getElementById("ampConnectingAvatar"),
      document.getElementById("ampChatAvatarImg"),
    ];
    avatarImgs.forEach(function (img) {
      if (img) {
        img.src = agent.avatar;
        img.alt = agent.name;
      }
    });

    const nameEl = document.getElementById("ampChatAgentName");
    const statusEl = document.getElementById("ampChatAgentStatus");
    if (nameEl) nameEl.textContent = agent.name;
    if (statusEl) statusEl.textContent = agent.role;
  }

  function esc(s) {
    if (!s) return "";
    return String(s).replace(/[&<>"']/g, function (m) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[m];
    });
  }

  function t(key, vars) {
    if (typeof window.ampSiteT === "function") {
      const val = window.ampSiteT(key, vars);
      if (val !== null && val !== undefined) return val;
    }
    return "";
  }

  function uiLang() {
    return localStorage.getItem("amp_ui_lang") || site.uiLang || "bn";
  }

  function getChatSessionId() {
    let sid = sessionStorage.getItem("amp_chat_sid");
    if (!sid) {
      sid = "sess_" + Math.random().toString(36).substring(2, 9) + "_" + Date.now().toString(36);
      sessionStorage.setItem("amp_chat_sid", sid);
    }
    return sid;
  }

  function refreshFeatures() {
    const lang = uiLang();
    const grid = document.getElementById("featureGrid");
    if (!grid || !site.features) return;
    grid.querySelectorAll("[data-feat-id]").forEach(function (card) {
      const id = card.getAttribute("data-feat-id");
      const feat = site.features.find(function (f) { return f.id === id; });
      if (!feat) return;
      const pack = (feat.langs && (feat.langs[lang] || feat.langs.en)) || {};
      const title = card.querySelector(".feature-title");
      const detail = card.querySelector(".feature-detail");
      const img = card.querySelector(".feature-img");
      if (title && pack.title) title.textContent = pack.title;
      if (detail && pack.detail) detail.textContent = pack.detail;
      if (img && pack.title) img.alt = pack.title;
    });
  }

  function refreshChatWidgetText() {
    const input = document.getElementById("ampChatInput");
    if (input) {
      const ph = t("agent_placeholder");
      if (ph) input.placeholder = ph;
    }

    const sendBtn = document.querySelector("#ampChatForm button");
    if (sendBtn) {
      const st = t("agent_send");
      if (st) sendBtn.textContent = st;
    }

    const tabSoft = document.getElementById("tabSoftwareBtn");
    if (tabSoft) {
      const ts = t("tab_software");
      if (ts) tabSoft.textContent = ts;
    }

    const tabGpro = document.getElementById("tabGoogleProBtn");
    if (tabGpro) {
      const tg = t("tab_google_pro");
      if (tg) tabGpro.textContent = tg;
    }
  }

  const ENGINE_PLANS = {
    video_studio: {
      price: 3999,
      title: "AutoMovie Pro - Social Media Content Automation Engine (Lifetime License)",
      displayTitle: "১. Social Media Content Automation Engine",
      note: "Social Media Engine — লাইফটাইম লাইসেন্স (ইংরেজি + ১টি ব্যক্তিগত ভাষা অন্তর্ভুক্ত)"
    },
    fb_business: {
      price: 2999,
      title: "AutoMovie Pro - FB Business Manager & Ad Automation Engine (Lifetime License)",
      displayTitle: "২. FB Business Manager & Ad Automation Engine",
      note: "FB Business Manager & Ad Engine — লাইফটাইম লাইসেন্স (আনলিমিটেড প্রোডাক্ট ও সেলস ব্যানার)"
    },
    profile_page: {
      price: 1999,
      title: "AutoMovie Pro - FB Profile & Page Post Automation Engine (Lifetime License)",
      displayTitle: "৩. FB Profile & Page Post Automation Engine",
      note: "FB Profile & Page Post Engine — লাইফটাইম লাইসেন্স (১০০% হিউম্যান সিমুলেশন পোস্টিং)"
    },
    wa_marketing: {
      price: 999,
      title: "WAManager Pro — WhatsApp Marketing Suite (১ বছর সাবস্ক্রিপশন + নিয়মিত ফিচার আপডেট)",
      displayTitle: "৪. WAManager Pro — WhatsApp Marketing & CRM Suite",
      note: "WhatsApp Marketing Suite — ১ বছর সাবস্ক্রিপশন (আনলিমিটেড বাল্ক মেসেজিং, বট ও বি২বি লিডস)"
    }
  };

  function getSelectedEngine() {
    const radio = document.querySelector('input[name="product_type"]:checked');
    const val = radio ? radio.value : "video_studio";
    return ENGINE_PLANS[val] || ENGINE_PLANS.video_studio;
  }

  const BN_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];
  function toBnDigits(num) {
    return String(num).replace(/[0-9]/g, function (d) { return BN_DIGITS[d]; });
  }

  function formatMoney(num) {
    const currentLang = (window.i18n && window.i18n.currentLang) || "bn";
    if (currentLang === "bn") {
      return "৳" + toBnDigits(num);
    }
    return "৳" + String(num).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function calcTotal() {
    const personal = document.querySelector('input[name="personal_lang"]:checked');
    const personalCode = personal ? personal.value : "bn";
    const extras = [];
    document.querySelectorAll('input[name="extra_langs[]"]').forEach(function (cb) {
      const wrap = cb.closest(".chip-addon");
      if (wrap) {
        wrap.style.display = cb.value === personalCode ? "none" : "";
        if (cb.value === personalCode) cb.checked = false;
      }
      if (cb.checked && cb.value !== personalCode) extras.push(cb.value);
    });

    const engine = getSelectedEngine();
    const basePrice = engine.price;
    let total = Number(basePrice) + Number(site.addon || 499) * extras.length;
    if (activeCoupon && activeCoupon.discount) {
      total = Math.max(0, total - Number(activeCoupon.discount));
    }
    const amountEl = document.getElementById("orderAmount");
    const planNameEl = document.getElementById("orderPlanName");
    const totalEl = document.getElementById("totalDisplay");
    const baseEl = document.getElementById("baseLangs");
    const addonEl = document.getElementById("addonLangs");
    const heroPriceEl = document.getElementById("heroSelectedPrice");
    const heroPlanNameEl = document.getElementById("heroSelectedPlanName");
    const heroPlanNoteEl = document.getElementById("heroSelectedPlanNote");

    if (amountEl) amountEl.value = String(total);
    if (planNameEl) planNameEl.value = engine.title;

    const formattedPrice = formatMoney(total);
    if (totalEl) totalEl.textContent = formattedPrice;
    if (heroPriceEl) heroPriceEl.textContent = formattedPrice;
    if (heroPlanNameEl) heroPlanNameEl.textContent = engine.displayTitle;
    if (heroPlanNoteEl) heroPlanNoteEl.textContent = engine.note;

    if (baseEl) baseEl.value = "en," + personalCode;
    if (addonEl) addonEl.value = extras.join(",");
  }

  window.selectEngineRadio = function (engineVal) {
    const radio = document.querySelector('input[name="product_type"][value="' + engineVal + '"]');
    if (radio) {
      radio.checked = true;
      document.querySelectorAll(".engine-select-card").forEach(function (card) {
        if (card.getAttribute("data-engine") === engineVal) {
          card.classList.add("active");
        } else {
          card.classList.remove("active");
        }
      });
      document.querySelectorAll(".tier-summary-chip").forEach(function (chip) {
        if (chip.getAttribute("data-engine-pill") === engineVal) {
          chip.classList.add("is-active");
        } else {
          chip.classList.remove("is-active");
        }
      });
      calcTotal();
    }
  };

  window.switchWorkflowTab = function (engineKey) {
    const targetMap = {
      engine_social: "wfBoxSocial",
      engine_business: "wfBoxBusiness",
      engine_profile: "wfBoxProfile",
      engine_whatsapp: "wfBoxWhatsApp"
    };
    const targetId = targetMap[engineKey] || "how";
    const el = document.getElementById(targetId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  window.filterEcosystem = function (filterKey) {
    document.querySelectorAll(".ecosystem-tab-btn").forEach(function (btn) {
      btn.classList.remove("active");
    });
    const activeBtnMap = {
      all: "btnEcoAll",
      video_studio: "btnEcoVideo",
      fb_business: "btnEcoBusiness",
      profile_page: "btnEcoProfile",
      wa_marketing: "btnEcoWa",
      google_pro: "btnEcoGpro"
    };
    const targetBtn = document.getElementById(activeBtnMap[filterKey]);
    if (targetBtn) targetBtn.classList.add("active");

    if (filterKey === 'google_pro') {
      const gproSection = document.getElementById('google-pro');
      if (gproSection) gproSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    const cards = document.querySelectorAll("#enginesGrid [data-engine-card]");
    cards.forEach(function (card) {
      const cardType = card.getAttribute("data-engine-card");
      if (filterKey === "all" || cardType === filterKey) {
        card.style.display = "flex";
        if (filterKey !== "all") {
          card.style.transform = "scale(1.02)";
          card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          card.style.transform = "";
        }
      } else {
        card.style.display = "none";
      }
    });
  };

  function appendChat(role, text, onComplete, checkoutUrl) {
    const log = document.getElementById("ampChatLog");
    if (!log) return;
    const div = document.createElement("div");
    div.className = "amp-chat-bubble amp-chat-" + role;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;

    if (role === "user") {
      const textSpan = document.createElement("div");
      textSpan.textContent = text;
      div.appendChild(textSpan);

      const statusMeta = document.createElement("div");
      statusMeta.className = "msg-status-meta";
      statusMeta.innerHTML = '<span class="status-tick">✓</span> <span class="status-label">পাঠানো হয়েছে</span>';
      div.appendChild(statusMeta);

      // Exactly 1 second (1000ms) after sending, status changes to "দেখা হয়েছে"
      setTimeout(function () {
        statusMeta.innerHTML = '<span class="status-tick is-seen">✓✓</span> <span class="status-label">দেখা হয়েছে</span>';
      }, 1000);

      if (onComplete) onComplete();
      return;
    }

    // Realistic human letter-by-letter live simulation (Letter by letter forming words live as user reads)
    AmpChatAudio.playReceived();
    const textSpan = document.createElement("span");
    textSpan.className = "bot-msg-text";
    div.appendChild(textSpan);

    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    div.appendChild(cursor);

    const chars = Array.from(text);
    let idx = 0;
    let isFinished = false;

    function finishTyping() {
      if (isFinished) return;
      isFinished = true;
      textSpan.textContent = text;
      if (cursor && cursor.parentNode) cursor.remove();
      log.scrollTop = log.scrollHeight;

      if (checkoutUrl) {
        const ctaWrap = document.createElement("div");
        ctaWrap.style.cssText = "margin-top:10px; padding-top:8px; border-top:1px dashed rgba(255,255,255,0.2);";
        const ctaBtn = document.createElement("a");
        ctaBtn.href = checkoutUrl;
        ctaBtn.className = "amp-chat-cta-btn";
        ctaBtn.style.cssText = "display:inline-flex; align-items:center; gap:6px; background:linear-gradient(135deg, #10b981, #059669); color:#ffffff; font-weight:700; font-size:0.85rem; padding:8px 14px; border-radius:6px; text-decoration:none; box-shadow:0 2px 8px rgba(16,185,129,0.3);";
        ctaBtn.innerHTML = "🎟️ ৳৫০০ নগদ ছাড়ে এখনই অর্ডার করুন →";
        ctaWrap.appendChild(ctaBtn);
        div.appendChild(ctaWrap);
        log.scrollTop = log.scrollHeight;
      }
      if (onComplete) onComplete();
    }

    // Allow user to click bubble to instantly complete typing
    div.addEventListener("click", function () {
      if (!isFinished && idx < chars.length) {
        finishTyping();
      }
    });

    function typeNextChar() {
      if (isFinished) return;
      if (idx < chars.length) {
        textSpan.textContent += chars[idx];
        const currentChar = chars[idx];
        idx++;
        log.scrollTop = log.scrollHeight;

        // Realistic deliberate human Bengali typing pace (slower, organic letter-by-letter)
        // Average keystroke delay: 52ms - 72ms per character
        let delay = Math.floor(Math.random() * 21) + 52;

        // Spacebar pause between words: +80ms - 130ms (so total ~130ms - 190ms)
        if (currentChar === " ") {
          delay += Math.floor(Math.random() * 51) + 80;
        }
        // Brief comma/dash pause: +160ms - 220ms (so total ~220ms - 280ms)
        else if (currentChar === "," || currentChar === "—" || currentChar === "-" || currentChar === ":") {
          delay += Math.floor(Math.random() * 61) + 160;
        }
        // Sentence ending pause (দাঁড়ি '।', '?', '!', newline): +280ms - 380ms (so total ~340ms - 440ms)
        else if (currentChar === "।" || currentChar === "?" || currentChar === "!" || currentChar === "\n") {
          delay += Math.floor(Math.random() * 101) + 280;
        }

        setTimeout(typeNextChar, delay);
      } else {
        finishTyping();
      }
    }

    typeNextChar();
  }

  function addSuggestions(items) {
    const log = document.getElementById("ampChatLog");
    if (!log || !items || !items.length) return;

    // Clear old suggestions so chat stays neat
    const oldRows = log.querySelectorAll(".amp-chat-suggestions");
    oldRows.forEach(function (r) { r.remove(); });

    const row = document.createElement("div");
    row.className = "amp-chat-suggestions";
    items.forEach(function (s) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = s;
      b.onclick = function () { sendChat(s); };
      row.appendChild(b);
    });
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  async function sendChat(text, opts) {
    const options = opts || {};
    const input = document.getElementById("ampChatInput");
    const msg = (text || (input && input.value) || "").trim();
    const isGreet = !!options.greet;
    let currentAgent = options.agent || getAssignedAgent();

    renderSavedHistoryToUI();

    if (!isGreet && !msg) return;
    if (input && !isGreet) input.value = "";
    if (!isGreet) {
      appendChat("user", msg);
      AmpChatAudio.playSent();
      history.push({ role: "user", content: msg });
      const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      appendToSavedHistory({ role: "user", content: msg, time: nowTime });
    }

    const sendTime = Date.now();
    let thinking = null;

    if (!isGreet) {
      // 1. User sees "পাঠানো হয়েছে", then exactly after 1 second (1000ms) "দেখা হয়েছে" appears
      // 2. Right after seen (at 1050ms), agent typing indicator appears ("নীরব লিখছেন…")
      setTimeout(function () {
        if (!thinking) {
          thinking = document.createElement("div");
          thinking.className = "amp-chat-bubble amp-chat-bot amp-chat-typing-indicator";
          thinking.innerHTML = "<span>" + esc(currentAgent.name) + " লিখছেন…</span> <span class=\"typing-dots\"><span></span><span></span><span></span></span>";
          const log = document.getElementById("ampChatLog");
          if (log) {
            log.appendChild(thinking);
            log.scrollTop = log.scrollHeight;
          }
          AmpChatAudio.playTypingStart();
        }
      }, 1050);
    } else {
      thinking = document.createElement("div");
      thinking.className = "amp-chat-bubble amp-chat-bot amp-chat-typing-indicator";
      thinking.innerHTML = "<span>" + esc(currentAgent.name) + " লিখছেন…</span> <span class=\"typing-dots\"><span></span><span></span><span></span></span>";
      const log = document.getElementById("ampChatLog");
      if (log) {
        log.appendChild(thinking);
        log.scrollTop = log.scrollHeight;
      }
      AmpChatAudio.playTypingStart();
    }

    try {
      const res = await fetch("/api/marketing-chat.php", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: isGreet ? "" : msg,
          action: isGreet ? "greet" : "chat",
          lang: uiLang(),
          visitor_id: getVisitorId(),
          agent_id: currentAgent.id,
          agent_name: currentAgent.name,
          agent_role: currentAgent.role,
          session_id: getChatSessionId(),
          history: history.slice(-8),
        }),
      });
      const data = await res.json();
      const reply = data.reply || (isGreet ? currentAgent.greet : "…");

      if (data.visitor_id) {
        try { localStorage.setItem(STORAGE_KEY_VID, data.visitor_id); } catch (e) {}
      }
      if (data.assigned_agent_id && data.assigned_agent_id !== currentAgent.id) {
        const syncedAgent = setAssignedAgent(data.assigned_agent_id);
        if (syncedAgent) currentAgent = syncedAgent;
      }

      // Timing choreography:
      // 0 - 1000ms: "পাঠানো হয়েছে" -> then "দেখা হয়েছে"
      // 1050ms - 1750ms: "নীরব লিখছেন…" indicator plays
      // 1750ms: live letter-by-letter typing simulation begins on screen!
      const minDelay = isGreet ? 200 : 1750;
      const elapsed = Date.now() - sendTime;
      const remainingWait = Math.max(50, minDelay - elapsed);

      setTimeout(function () {
        if (thinking && thinking.parentNode) thinking.remove();
        appendChat("bot", reply, function () {
          if (data.suggestions && data.suggestions.length) {
            addSuggestions(data.suggestions);
          } else {
            addSuggestions([
              t("agent_suggestion_1"),
              t("agent_suggestion_2"),
              t("agent_suggestion_3"),
            ]);
          }
        }, data.checkout_url);
        history.push({ role: "assistant", content: reply });
        const replyTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        appendToSavedHistory({ role: "bot", content: reply, time: replyTime, checkoutUrl: data.checkout_url || null });
      }, remainingWait);

      if (data.open_whatsapp && data.whatsapp_url) {
        setTimeout(function () {
          window.open(data.whatsapp_url, "_blank");
        }, 1500);
      }
    } catch (e) {
      if (thinking && thinking.parentNode) thinking.remove();
      appendChat("bot", isGreet ? currentAgent.greet : t("or_whatsapp"));
    }
  }

  async function handleApplyCoupon() {
    const input = document.getElementById("couponCodeInput");
    const msgEl = document.getElementById("couponStatusMsg");
    if (!input || !msgEl) return;
    const code = input.value.trim().toUpperCase();
    if (!code) {
      msgEl.className = "coupon-msg error";
      msgEl.textContent = t("coupon_empty_err");
      return;
    }
    msgEl.className = "coupon-msg";
    msgEl.textContent = t("coupon_checking");

    try {
      const amount = Number(document.getElementById("orderAmount")?.value || site.price);
      const res = await fetch("/api/validate_coupon.php", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code, amount: amount }),
      });
      const data = await res.json();
      if (data.ok) {
        activeCoupon = data;
        msgEl.className = "coupon-msg success";
        msgEl.textContent = `✓ ${data.message} (৳${data.discount})`;
        calcTotal();
      } else {
        activeCoupon = null;
        msgEl.className = "coupon-msg error";
        msgEl.textContent = data.message || "Invalid coupon code";
        calcTotal();
      }
    } catch (e) {
      msgEl.className = "coupon-msg error";
      msgEl.textContent = "Coupon validation failed.";
    }
  }

  // ---------------------------------------------------------------------------
  // DOM Ready Initializer & Open/Close Handlers
  // ---------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('input[name="personal_lang"]').forEach(function (el) {
      el.addEventListener("change", calcTotal);
    });
    document.querySelectorAll('input[name="extra_langs[]"]').forEach(function (cb) {
      cb.addEventListener("change", calcTotal);
    });
    document.querySelectorAll('input[name="product_type"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        window.selectEngineRadio(this.value);
      });
    });
    document.querySelectorAll(".engine-select-card").forEach(function (card) {
      card.addEventListener("click", function (e) {
        const radio = this.querySelector('input[type="radio"]');
        if (radio && e.target !== radio) {
          radio.checked = true;
          window.selectEngineRadio(radio.value);
        }
      });
    });
    document.querySelectorAll(".workflow-tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const target = this.getAttribute("data-engine-target");
        if (target) window.switchWorkflowTab(target);
      });
    });
    calcTotal();
    refreshFeatures();
    refreshChatWidgetText();

    document.addEventListener("amp-lang-change", function () {
      calcTotal();
      refreshFeatures();
      refreshChatWidgetText();
    });

    const launcher = document.getElementById("ampChatLauncher");
    const choiceCard = document.getElementById("ampChoiceCard");
    const choiceClose = document.getElementById("ampChoiceClose");
    const startLiveBtn = document.getElementById("ampStartLiveAgentBtn");
    const panel = document.getElementById("ampChatPanel");
    const chatBack = document.getElementById("ampChatBack");
    const chatClose = document.getElementById("ampChatClose");
    const form = document.getElementById("ampChatForm");

    // Assign team agent for this visitor
    const assignedAgent = getAssignedAgent();
    applyAgentToUI(assignedAgent);

    function closeAll() {
      if (choiceCard) {
        choiceCard.classList.add("is-hidden");
        choiceCard.style.display = "none";
      }
      if (panel) {
        panel.classList.add("is-hidden");
        panel.hidden = true;
        panel.style.display = "none";
      }
    }

    function openChoiceCard() {
      if (!choiceCard) return;
      if (panel) {
        panel.classList.add("is-hidden");
        panel.style.display = "none";
      }
      choiceCard.classList.remove("is-hidden");
      choiceCard.style.display = "flex";
      applyAgentToUI(getAssignedAgent());
    }

    function startConnectingSequence(agent, onComplete) {
      const overlay = document.getElementById("ampConnectingOverlay");
      const title = document.getElementById("ampConnectingTitle");
      const desc = document.getElementById("ampConnectingDesc");
      const prog = document.getElementById("ampConnectingProgress");

      const savedList = loadSavedChatHistory();
      const isReturningVisitor = savedList.length > 0;

      // Render saved history to UI before greeting
      renderSavedHistoryToUI();

      if (!overlay || panel.dataset.greeted) {
        if (overlay) overlay.style.display = "none";
        if (!panel.dataset.greeted) {
          panel.dataset.greeted = "1";
          sendChat("", { greet: true, agent: agent, isReturning: isReturningVisitor });
        }
        const inp = document.getElementById("ampChatInput");
        if (inp) setTimeout(function () { inp.focus(); }, 150);
        if (onComplete) onComplete();
        return;
      }

      overlay.style.display = "flex";
      overlay.style.opacity = "1";

      if (isReturningVisitor) {
        if (prog) prog.style.width = "40%";
        if (title) title.textContent = agent.name + " পুনরায় যুক্ত হচ্ছেন…";
        if (desc) desc.textContent = "👤 আপনার পূর্বের কনসালট্যান্ট " + agent.name + " (" + agent.role + ") সরাসরি যুক্ত হচ্ছেন...";

        // Step 2: Connection Restored (450ms)
        setTimeout(function () {
          if (prog) prog.style.width = "100%";
          if (title) title.textContent = "✅ লাইভ সংযোগ সক্রিয়!";
          if (desc) desc.textContent = agent.name + " আপনার সাথে সংযুক্ত হয়েছেন...";
          AmpChatAudio.playConnected();
        }, 450);
      } else {
        if (prog) prog.style.width = "40%";
        if (title) title.textContent = agent.name + " যুক্ত হচ্ছেন…";
        if (desc) desc.textContent = "👤 আপনার কাস্টমার কনসালট্যান্ট " + agent.name + " (" + agent.role + ") যুক্ত হচ্ছেন...";

        // Step 2: Connection Established (450ms)
        setTimeout(function () {
          if (prog) prog.style.width = "100%";
          if (title) title.textContent = "✅ লাইভ সংযোগ সক্রিয়!";
          if (desc) desc.textContent = agent.name + " আপনার সাথে সরাসরি সংযুক্ত হয়েছেন...";
          AmpChatAudio.playConnected();
        }, 450);
      }

      // Step 3: Fast smooth fade out (800ms total wait, 200ms fade)
      setTimeout(function () {
        overlay.style.opacity = "0";
        setTimeout(function () {
          overlay.style.display = "none";
          if (!panel.dataset.greeted) {
            panel.dataset.greeted = "1";
            sendChat("", { greet: true, agent: agent, isReturning: isReturningVisitor });
          }
          const inp = document.getElementById("ampChatInput");
          if (inp) inp.focus();
          if (onComplete) onComplete();
        }, 200);
      }, 800);
    }

    function openLiveChat() {
      if (!panel) return;
      AmpChatAudio.unlock();
      AmpChatAudio.updateSoundButtonUI();
      if (choiceCard) {
        choiceCard.classList.add("is-hidden");
        choiceCard.style.display = "none";
      }
      panel.classList.remove("is-hidden");
      panel.hidden = false;
      panel.style.display = "flex";
      applyAgentToUI(getAssignedAgent());
      startConnectingSequence(getAssignedAgent());
    }

    // Launcher click toggles choice card or closes active panel
    if (launcher) {
      launcher.onclick = function (e) {
        e.stopPropagation();
        AmpChatAudio.unlock();
        const isChoiceOpen = choiceCard && !choiceCard.classList.contains("is-hidden") && choiceCard.style.display !== "none";
        const isPanelOpen = panel && !panel.classList.contains("is-hidden") && panel.style.display !== "none";
        if (isChoiceOpen || isPanelOpen) {
          closeAll();
        } else {
          openChoiceCard();
        }
      };
    }

    if (choiceClose) {
      choiceClose.onclick = function (e) {
        e.stopPropagation();
        closeAll();
      };
    }

    if (startLiveBtn) {
      startLiveBtn.onclick = function (e) {
        e.stopPropagation();
        openLiveChat();
      };
    }

    if (chatBack) {
      chatBack.onclick = function (e) {
        e.stopPropagation();
        openChoiceCard();
      };
    }

    if (chatClose) {
      chatClose.onclick = function (e) {
        e.stopPropagation();
        closeAll();
      };
    }

    const soundToggleBtn = document.getElementById("ampChatSoundToggle");
    if (soundToggleBtn) {
      AmpChatAudio.updateSoundButtonUI();
      soundToggleBtn.onclick = function (e) {
        e.stopPropagation();
        AmpChatAudio.unlock();
        AmpChatAudio.toggleMute();
      };
    }

    const resetBtn = document.getElementById("ampChatReset");
    if (resetBtn) {
      resetBtn.onclick = function (e) {
        e.stopPropagation();
        if (confirm("আপনি কি পূর্ববর্তী চ্যাট মুছে ফেলে নতুন করে কথা শুরু করতে চান?")) {
          clearSavedHistory();
          history.length = 0;
          hasRenderedSavedHistory = false;
          const log = document.getElementById("ampChatLog");
          if (log) log.innerHTML = "";
          delete panel.dataset.greeted;
          try {
            sessionStorage.removeItem("amp_chat_sid");
          } catch (err) {}
          startConnectingSequence(getAssignedAgent());
        }
      };
    }

    // Close on Escape key
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        closeAll();
      }
    });

    if (form) {
      form.onsubmit = function (e) {
        e.preventDefault();
        sendChat();
      };
    }

    const applyBtn = document.getElementById("applyCouponBtn");
    if (applyBtn) {
      applyBtn.onclick = handleApplyCoupon;
    }
  });
})();
