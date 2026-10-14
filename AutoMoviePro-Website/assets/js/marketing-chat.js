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
      greet: "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro টিম থেকে বলছি। আপনাদের কীভাবে সাহায্য করতে পারি? আমাদের ৩টি প্যাকেজ, স্পেশাল অফার বা যেকোনো ফিচার সম্পর্কে জানতে চাইলে বলুন।"
    },
    {
      id: "nirob",
      name: "নীরব (Nirob)",
      role: "টেকনিক্যাল ও প্রোডাক্ট স্পেশালিস্ট",
      avatar: "/assets/img/agents/nirob.png",
      greet: "আসসালামু আলাইকুম! আমি নীরব, AutoMovie Pro টেকনিক্যাল সাপোর্ট থেকে বলছি। ইউটিউব, ফেসবুক বা টিকটক অটোমেশন সফটওয়্যার নিয়ে আপনার যেকোনো প্রশ্ন থাকলে বলুন, আমি বুঝিয়ে দিচ্ছি।"
    },
    {
      id: "tania",
      name: "তানিয়া (Tania)",
      role: "অনবোর্ডিং ও লাইসেন্স ম্যানেজার",
      avatar: "/assets/img/agents/tania.png",
      greet: "আসসালামু আলাইকুম! আমি তানিয়া। AutoMovie Pro লাইফটাইম লাইসেন্স প্যাকেজ, ডিসকাউন্ট কুপন বা পেমেন্ট ভেরিফিকেশন নিয়ে যেকোনো তথ্য জানতে আমাকে বলতে পারেন।"
    }
  ];

  function getAssignedAgent() {
    let savedId = localStorage.getItem("amp_assigned_agent_id");
    let agent = SUPPORT_TEAM.find(function (a) { return a.id === savedId; });
    if (!agent) {
      // Pick random agent from team for this visitor
      const idx = Math.floor(Math.random() * SUPPORT_TEAM.length);
      agent = SUPPORT_TEAM[idx];
      try {
        localStorage.setItem("amp_assigned_agent_id", agent.id);
      } catch (e) {}
    }
    return agent;
  }

  function applyAgentToUI(agent) {
    const avatarImg = document.getElementById("ampChatAvatarImg");
    const nameEl = document.getElementById("ampChatAgentName");
    const statusEl = document.getElementById("ampChatAgentStatus");
    if (avatarImg) {
      avatarImg.src = agent.avatar;
      avatarImg.alt = agent.name;
    }
    if (nameEl) nameEl.textContent = agent.name;
    if (statusEl) statusEl.textContent = agent.role;
  }

  function t(key, vars) {
    if (typeof window.ampSiteT === "function") {
      return window.ampSiteT(key, vars);
    }
    return key;
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
    const toggle = document.getElementById("ampChatToggle");
    if (toggle) {
      const dot = toggle.querySelector(".online-dot");
      toggle.innerHTML = "";
      if (dot) toggle.appendChild(dot);
      const span = document.createElement("span");
      span.textContent = " " + t("agent_toggle_btn");
      toggle.appendChild(span);
    }

    const input = document.getElementById("ampChatInput");
    if (input) input.placeholder = t("agent_placeholder");

    const sendBtn = document.querySelector("#ampChatForm button");
    if (sendBtn) sendBtn.textContent = t("agent_send");

    const waLink = document.getElementById("ampChatWa");
    if (waLink) waLink.textContent = t("agent_wa_link");

    const tabSoft = document.getElementById("tabSoftwareBtn");
    if (tabSoft) tabSoft.textContent = t("tab_software");

    const tabGpro = document.getElementById("tabGoogleProBtn");
    if (tabGpro) tabGpro.textContent = t("tab_google_pro");
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
    let total = Number(site.price) + Number(site.addon) * extras.length;
    if (activeCoupon && activeCoupon.discount) {
      total = Math.max(0, total - Number(activeCoupon.discount));
    }
    const amountEl = document.getElementById("orderAmount");
    const totalEl = document.getElementById("totalDisplay");
    const baseEl = document.getElementById("baseLangs");
    const addonEl = document.getElementById("addonLangs");
    if (amountEl) amountEl.value = String(total);
    if (totalEl) totalEl.textContent = "৳" + total;
    if (baseEl) baseEl.value = "en," + personalCode;
    if (addonEl) addonEl.value = extras.join(",");
  }

  function appendChat(role, text) {
    const log = document.getElementById("ampChatLog");
    if (!log) return;
    const div = document.createElement("div");
    div.className = "amp-chat-bubble amp-chat-" + role;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function addSuggestions(items) {
    const log = document.getElementById("ampChatLog");
    if (!log || !items || !items.length) return;
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
    const currentAgent = options.agent || getAssignedAgent();

    if (!isGreet && !msg) return;
    if (input && !isGreet) input.value = "";
    if (!isGreet) {
      appendChat("user", msg);
      history.push({ role: "user", content: msg });
    }

    const thinking = document.createElement("div");
    thinking.className = "amp-chat-bubble amp-chat-bot";
    thinking.textContent = "…";
    const log = document.getElementById("ampChatLog");
    if (log) {
      log.appendChild(thinking);
      log.scrollTop = log.scrollHeight;
    }

    try {
      const res = await fetch("/api/marketing-chat.php", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: isGreet ? "" : msg,
          action: isGreet ? "greet" : "chat",
          lang: uiLang(),
          agent_id: currentAgent.id,
          agent_name: currentAgent.name,
          agent_role: currentAgent.role,
          session_id: getChatSessionId(),
          history: history.slice(-8),
        }),
      });
      const data = await res.json();
      if (thinking.parentNode) thinking.remove();
      const reply = data.reply || (isGreet ? currentAgent.greet : "…");
      appendChat("bot", reply);
      history.push({ role: "assistant", content: reply });
      if (data.suggestions && data.suggestions.length) {
        addSuggestions(data.suggestions);
      } else {
        addSuggestions([
          t("agent_suggestion_1"),
          t("agent_suggestion_2"),
          t("agent_suggestion_3"),
          t("agent_suggestion_4"),
        ]);
      }
      if (data.open_whatsapp && data.whatsapp_url) {
        setTimeout(function () {
          window.open(data.whatsapp_url, "_blank");
        }, 1500);
      }
    } catch (e) {
      if (thinking.parentNode) thinking.remove();
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
    calcTotal();
    refreshFeatures();
    refreshChatWidgetText();

    document.addEventListener("amp-lang-change", function () {
      refreshFeatures();
      refreshChatWidgetText();
    });

    const toggle = document.getElementById("ampChatToggle");
    const panel = document.getElementById("ampChatPanel");
    const close = document.getElementById("ampChatClose");
    const form = document.getElementById("ampChatForm");

    // Assign team agent for this visitor
    const assignedAgent = getAssignedAgent();
    applyAgentToUI(assignedAgent);

    function openChat() {
      if (!panel) return;
      panel.classList.remove("is-hidden");
      panel.hidden = false;
      panel.style.display = "flex";
      applyAgentToUI(getAssignedAgent());
      if (!panel.dataset.greeted) {
        panel.dataset.greeted = "1";
        sendChat("", { greet: true, agent: assignedAgent });
      }
      const inp = document.getElementById("ampChatInput");
      if (inp) setTimeout(function () { inp.focus(); }, 150);
    }

    function closeChat() {
      if (!panel) return;
      panel.classList.add("is-hidden");
      panel.hidden = true;
      panel.style.display = "none";
    }

    if (toggle) {
      toggle.onclick = function (e) {
        e.stopPropagation();
        const isHidden = panel.classList.contains("is-hidden") || panel.hidden || panel.style.display === "none";
        if (isHidden) {
          openChat();
        } else {
          closeChat();
        }
      };
    }

    if (close) {
      close.onclick = function (e) {
        e.stopPropagation();
        closeChat();
      };
    }

    // Close on Escape key
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panel && !panel.hidden && panel.style.display !== "none") {
        closeChat();
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
