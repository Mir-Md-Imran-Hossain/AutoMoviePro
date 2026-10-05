(function () {
  const site = window.AMP_SITE || { price: 2998, addon: 499, features: [], waLink: "" };
  const draft = { name: "", whatsapp: "", personal_lang: "", extras: [], step: "chat" };
  const history = [];
  let activeCoupon = null;

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
        addSuggestions(["প্যাকেজের দাম কত?", "পেমেন্ট কিভাবে করব?", "কুপন কোড দিন", "কিভাবে ভিডিও বানায়?"]);
      }
      if (data.open_whatsapp && data.whatsapp_url) {
        setTimeout(() => {
          window.open(data.whatsapp_url, "_blank");
        }, 1500);
      }
    } catch (e) {
      if (thinking.parentNode) thinking.remove();
      appendChat("bot", "নেটওয়ার্ক সমস্যা। সরাসরি আমাদের WhatsApp নম্বরে নক করুন।");
    }
  }

  async function handleApplyCoupon() {
    const input = document.getElementById("couponCodeInput");
    const msgEl = document.getElementById("couponStatusMsg");
    if (!input || !msgEl) return;
    const code = input.value.trim().toUpperCase();
    if (!code) {
      msgEl.className = "coupon-msg error";
      msgEl.textContent = "অনুগ্রহ করে একটি কুপন কোড লিখুন।";
      return;
    }
    msgEl.className = "coupon-msg";
    msgEl.textContent = "যাচাই করা হচ্ছে...";

    try {
      const amount = Number(document.getElementById("orderAmount")?.value || site.price);
      const res = await fetch("/api/validate_coupon.php", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code, amount: amount })
      });
      const data = await res.json();
      if (data.ok) {
        activeCoupon = data;
        msgEl.className = "coupon-msg success";
        msgEl.textContent = `✓ ${data.message} (ছাড়: ৳${data.discount})`;
        calcTotal();
      } else {
        activeCoupon = null;
        msgEl.className = "coupon-msg error";
        msgEl.textContent = `✗ ${data.error || 'ভুল কুপন কোড'}`;
        calcTotal();
      }
    } catch (err) {
      msgEl.className = "coupon-msg error";
      msgEl.textContent = "কুপন সার্ভারে কানেক্ট করা যায়নি।";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (site.uiLang) {
      localStorage.setItem("amp_ui_lang", site.uiLang);
    }
    document.querySelectorAll('input[name="personal_lang"], input[name="extra_langs[]"]').forEach((el) => {
      el.addEventListener("change", calcTotal);
    });
    calcTotal();
    refreshFeatures();
    document.addEventListener("amp-lang-change", refreshFeatures);

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
    if (close && panel) close.onclick = () => { panel.hidden = true; };
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
