(function () {
  const site = window.AMP_SITE || { price: 2998, addon: 499, features: [], waLink: "" };
  const history = [];
  let activeCoupon = null;

  function t(key, vars) {
    if (typeof window.ampSiteT === "function") {
      return window.ampSiteT(key, vars);
    }
    return key;
  }

  function uiLang() {
    return localStorage.getItem("amp_ui_lang") || site.uiLang || "bn";
  }

  function refreshFeatures() {
    const lang = uiLang();
    const grid = document.getElementById("featureGrid");
    if (!grid || !site.features) return;
    grid.querySelectorAll("[data-feat-id]").forEach((card) => {
      const id = card.getAttribute("data-feat-id");
      const feat = site.features.find((f) => f.id === id);
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

    const nameEl = document.querySelector(".amp-chat-name strong");
    if (nameEl) nameEl.textContent = t("agent_name");

    const statusEl = document.querySelector(".amp-chat-name span");
    if (statusEl) {
      statusEl.innerHTML = '<span class="online-dot" style="width:6px; height:6px;"></span> ' + t("agent_status");
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
    document.querySelectorAll('input[name="extra_langs[]"]').forEach((cb) => {
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
    items.forEach((s) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = s;
      b.onclick = () => sendChat(s);
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
          history: history.slice(-8),
        }),
      });
      const data = await res.json();
      if (thinking.parentNode) thinking.remove();
      const reply = data.reply || "…";
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
        setTimeout(() => {
          window.open(data.whatsapp_url, "_blank");
        }, 1500);
      }
    } catch (e) {
      if (thinking.parentNode) thinking.remove();
      appendChat("bot", t("or_whatsapp"));
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

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('input[name="personal_lang"]').forEach((el) => {
      el.addEventListener("change", calcTotal);
    });
    document.querySelectorAll('input[name="extra_langs[]"]').forEach((el) => {
      el.addEventListener("change", calcTotal);
    });
    calcTotal();
    refreshFeatures();
    refreshChatWidgetText();

    document.addEventListener("amp-lang-change", () => {
      refreshFeatures();
      refreshChatWidgetText();
    });

    const toggle = document.getElementById("ampChatToggle");
    const panel = document.getElementById("ampChatPanel");
    const close = document.getElementById("ampChatClose");
    const form = document.getElementById("ampChatForm");
    if (toggle && panel) {
      toggle.onclick = () => {
        panel.hidden = !panel.hidden;
        if (!panel.hidden && !panel.dataset.greeted) {
          panel.dataset.greeted = "1";
          sendChat("", { greet: true });
        }
      };
    }
    if (close && panel) {
      close.onclick = () => {
        panel.hidden = true;
      };
    }
    if (form) {
      form.onsubmit = (e) => {
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
