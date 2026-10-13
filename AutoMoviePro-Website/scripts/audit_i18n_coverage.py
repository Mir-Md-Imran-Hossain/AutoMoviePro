import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

html_keys = set()
for fpath in ['AutoMoviePro-Website/index.php', 'AutoMoviePro-Website/order.php', 'AutoMoviePro-Website/pending.php']:
    text = open(fpath, encoding='utf-8').read()
    keys = re.findall(r'data-i18n=["\']([^"\']+)["\']', text)
    html_keys.update(keys)

# Also check chat JS keys
chat_text = open('AutoMoviePro-Website/assets/js/marketing-chat.js', encoding='utf-8').read()
chat_keys = re.findall(r't\(["\']([^"\']+)["\']', chat_text)
html_keys.update(chat_keys)

print(f"Total unique i18n keys required: {len(html_keys)}")

js_text = open('AutoMoviePro-Website/assets/js/i18n-site.js', encoding='utf-8').read()
langs = ['bn', 'en', 'hi', 'ur', 'ta', 'ml']
missing_per_lang = {l: [] for l in langs}

for lang in langs:
    # Match lang: { ... }
    m = re.search(r'\b' + lang + r'\s*:\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', js_text)
    if not m:
        print(f"ERROR: Lang {lang} block not found!")
        continue
    block = m.group(1)
    keys_in_lang = set(re.findall(r'([a-zA-Z0-9_]+)\s*:', block))
    for k in sorted(html_keys):
        if k not in keys_in_lang:
            missing_per_lang[lang].append(k)

all_perfect = True
for lang in langs:
    if missing_per_lang[lang]:
        all_perfect = False
        print(f"❌ Missing in {lang} ({len(missing_per_lang[lang])}):", missing_per_lang[lang])
    else:
        print(f"✅ {lang.upper()}: 100% complete! ({len(html_keys)} / {len(html_keys)} keys covered)")

if all_perfect:
    print("\n🎉 PERFECT COVERAGE: All templates and interactive widgets have 100% translation coverage in all 6 languages!")
