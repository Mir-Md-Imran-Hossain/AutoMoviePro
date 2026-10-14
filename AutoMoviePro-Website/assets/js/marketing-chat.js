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
      title: "AutoMovie Pro - Social Media Content Automation Engine (Lifetime License)"
    },
    fb_business: {
      price: 2999,
      title: "AutoMovie Pro - FB Business Manager & Ad Automation Engine (Lifetime License)"
    },
    profile_page: {
      price: 1999,
      title: "AutoMovie Pro - FB Profile & Page Post Automation Engine (Lifetime License)"
    }
  };

  function getSelectedEngine() {
    const radio = document.querySelector('input[name="product_type"]:checked');
    const val = radio ? radio.value : "video_studio";
    return ENGINE_PLANS[val] || ENGINE_PLANS.video_studio;
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
    if (amountEl) amountEl.value = String(total);
    if (planNameEl) planNameEl.value = engine.title;
    if (totalEl) totalEl.textContent = "৳" + total;
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
      calcTotal();
    }
  };

  window.switchWorkflowTab = function (engineKey) {
    const tabs = [
      {
        key: "engine_social",
        btn: "wfTabSocial",
        pane: "pane_engine_social",
        titleKey: "how_it_works",
        titleDef: "Automovie Pro - Social Media Content Automation Engine কিভাবে কাজ করে?",
        leadDef: "সম্পূর্ণ স্বয়ংক্রিয় ৯টি ধাপে ভাইরাল কনটেন্ট রিসার্চ থেকে শুরু করে ভিডিও তৈরি, গ্লোবাল ট্রান্সলেশন ও মাল্টি-প্ল্যাটফর্ম পাবলিশিং।"
      },
      {
        key: "engine_business",
        btn: "wfTabBusiness",
        pane: "pane_engine_business",
        titleKey: "how_engine2_title",
        titleDef: "Automovie Pro - FB Business Manager & Ad Automation Engine কিভাবে কাজ করে?",
        leadDef: "৫টি নিখুঁত পদক্ষেপে প্রোডাক্ট ও সার্ভিসের সেলস ব্যানার, অ্যাড ভিডিও ও কাস্টমার রেসপন্স।"
      },
      {
        key: "engine_profile",
        btn: "wfTabProfile",
        pane: "pane_engine_profile",
        titleKey: "how_engine3_title",
        titleDef: "Automovie Pro - FB Profile & Page Post Automation Engine কিভাবে কাজ করে?",
        leadDef: "৫টি পবিত্র ও পরিচ্ছন্ন ধাপে ইসলামিক বা অনুপ্রেরণামূলক পোস্ট ও ব্যানার অটো-পাইলট পাবলিশিং।"
      }
    ];

    tabs.forEach(function (item) {
      const btn = document.getElementById(item.btn);
      const pane = document.getElementById(item.pane);
      if (item.key === engineKey) {
        if (btn) btn.classList.add("active");
        if (pane) {
          pane.style.display = "block";
          pane.classList.add("active");
        }
        const titleEl = document.getElementById("howMainTitle");
        const leadEl = document.getElementById("howMainLead");
        if (titleEl) {
          titleEl.textContent = t(item.titleKey) || item.titleDef;
          titleEl.setAttribute("data-i18n", item.titleKey);
        }
        if (leadEl) {
          leadEl.textContent = item.leadDef;
        }
      } else {
        if (btn) btn.classList.remove("active");
        if (pane) {
          pane.style.display = "none";
          pane.classList.remove("active");
        }
      }
    });

    const howSec = document.getElementById("how");
    if (howSec) {
      howSec.scrollIntoView({ behavior: "smooth", block: "start" });
    }
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

      // Simulate human seen receipt after 750ms
      setTimeout(function () {
        statusMeta.innerHTML = '<span class="status-tick is-seen">✓✓</span> <span class="status-label">দেখা হয়েছে</span>';
      }, 750);

      if (onComplete) onComplete();
      return;
    }

    // Realistic human word-by-word typing effect for bot replies
    const words = text.split(/(\s+)/);
    let idx = 0;

    function typeNextWord() {
      if (idx < words.length) {
        div.textContent += words[idx];
        idx++;
        log.scrollTop = log.scrollHeight;

        let delay = Math.floor(Math.random() * 22) + 18;
        const last = words[idx - 1];
        if (last && (last.includes("।") || last.includes("?") || last.includes("!") || last.includes("\n"))) {
          delay += 110;
        } else if (last && (last.includes(",") || last.includes(";"))) {
          delay += 60;
        }
        setTimeout(typeNextWord, delay);
      } else {
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
    }

    typeNextWord();
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
    const currentAgent = options.agent || getAssignedAgent();

    if (!isGreet && !msg) return;
    if (input && !isGreet) input.value = "";
    if (!isGreet) {
      appendChat("user", msg);
      history.push({ role: "user", content: msg });
    }

    const sendTime = Date.now();
    let thinking = null;

    if (!isGreet) {
      // Realistic human reaction delay before typing starts (after 750ms seen mark)
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
        }
      }, 800);
    } else {
      thinking = document.createElement("div");
      thinking.className = "amp-chat-bubble amp-chat-bot amp-chat-typing-indicator";
      thinking.innerHTML = "<span>" + esc(currentAgent.name) + " যুক্ত হচ্ছেন…</span> <span class=\"typing-dots\"><span></span><span></span><span></span></span>";
      const log = document.getElementById("ampChatLog");
      if (log) {
        log.appendChild(thinking);
        log.scrollTop = log.scrollHeight;
      }
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
      const reply = data.reply || (isGreet ? currentAgent.greet : "…");

      const minDelay = isGreet ? 400 : 1350;
      const elapsed = Date.now() - sendTime;
      const remainingWait = Math.max(200, minDelay - elapsed);

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

      if (!overlay || panel.dataset.greeted) {
        if (overlay) overlay.style.display = "none";
        if (!panel.dataset.greeted) {
          panel.dataset.greeted = "1";
          sendChat("", { greet: true, agent: agent });
        }
        const inp = document.getElementById("ampChatInput");
        if (inp) setTimeout(function () { inp.focus(); }, 150);
        if (onComplete) onComplete();
        return;
      }

      overlay.style.display = "flex";
      overlay.style.opacity = "1";
      if (prog) prog.style.width = "15%";
      if (title) title.textContent = "লাইভ সাপোর্ট সক্রিয় হচ্ছে…";
      if (desc) desc.textContent = "🔄 আপনার জন্য একজন কাস্টমার কনসালট্যান্ট নির্ধারণ করা হচ্ছে...";

      // Step 2: Agent Assigned (700ms)
      setTimeout(function () {
        if (prog) prog.style.width = "65%";
        if (title) title.textContent = agent.name + " দায়িত্ব নিচ্ছেন…";
        if (desc) desc.textContent = "👤 " + agent.name + " (" + agent.role + ") আপনার চ্যাটের দায়িত্ব গ্রহণ করেছেন...";
      }, 700);

      // Step 3: Connection Established (1400ms)
      setTimeout(function () {
        if (prog) prog.style.width = "100%";
        if (title) title.textContent = "✅ লাইভ সংযোগ স্থাপিত!";
        if (desc) desc.textContent = "এখনই চ্যাট শুরু হচ্ছে...";
      }, 1400);

      // Step 4: Fade out and greet (1750ms)
      setTimeout(function () {
        overlay.style.opacity = "0";
        setTimeout(function () {
          overlay.style.display = "none";
          if (!panel.dataset.greeted) {
            panel.dataset.greeted = "1";
            sendChat("", { greet: true, agent: agent });
          }
          const inp = document.getElementById("ampChatInput");
          if (inp) inp.focus();
          if (onComplete) onComplete();
        }, 350);
      }, 1750);
    }

    function openLiveChat() {
      if (!panel) return;
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
