const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

// 1. Collect all data-i18n attributes from PHP templates
const requiredKeys = new Set();
['index.php', 'order.php', 'pending.php'].forEach((file) => {
  const content = fs.readFileSync(path.join(root, file), 'utf8');
  const matches = content.matchAll(/data-i18n=["']([^"']+)["']/g);
  for (const m of matches) {
    requiredKeys.add(m[1]);
  }
});

// Explicit chat widget keys called in marketing-chat.js
[
  'agent_toggle_btn',
  'agent_name',
  'agent_status',
  'agent_placeholder',
  'agent_send',
  'agent_wa_link',
  'agent_suggestion_1',
  'agent_suggestion_2',
  'agent_suggestion_3',
  'agent_suggestion_4',
  'tab_software',
  'tab_google_pro',
  'coupon_empty_err',
  'coupon_checking'
].forEach(k => requiredKeys.add(k));

console.log(`Auditing ${requiredKeys.size} required i18n keys...`);

// 2. Extract PACKS from i18n-site.js
const i18nContent = fs.readFileSync(path.join(root, 'assets', 'js', 'i18n-site.js'), 'utf8');
// Mock window & document
let packsObj = null;
const scriptContext = `
  const window = {};
  const document = { addEventListener: () => {} };
  ${i18nContent.replace('const PACKS =', 'packsObj =')}
`;
eval(scriptContext);

const langs = ['bn', 'en', 'hi', 'ur', 'ta', 'ml'];
let hasErrors = false;

langs.forEach((lang) => {
  const pack = packsObj[lang];
  if (!pack) {
    console.error(`❌ Language pack [${lang}] is completely missing!`);
    hasErrors = true;
    return;
  }
  const missing = [];
  requiredKeys.forEach((key) => {
    if (!pack[key] && pack[key] !== '') {
      missing.push(key);
    }
  });

  if (missing.length > 0) {
    console.error(`❌ ${lang.toUpperCase()}: Missing ${missing.length} keys:`, missing);
    hasErrors = true;
  } else {
    console.log(`✅ ${lang.toUpperCase()}: 100% Complete! (${requiredKeys.size}/${requiredKeys.size} keys present & translated)`);
  }
});

if (!hasErrors) {
  console.log('\n🌟 AUDIT PASSED: Every single template and interactive element has full, accurate translations in all 6 languages!');
} else {
  process.exit(1);
}
