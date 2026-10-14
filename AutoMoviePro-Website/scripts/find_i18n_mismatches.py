import re

with open('index.php', 'r', encoding='utf-8') as f:
    index_html = f.read()

with open('assets/js/i18n-site.js', 'r', encoding='utf-8') as f:
    js_text = f.read()

tags = re.findall(r'<([a-zA-Z0-9]+)[^>]*data-i18n=[\x22\x27]([^\x22\x27]+)[\x22\x27][^>]*>(.*?)</\1>', index_html, re.DOTALL)

bn_start = js_text.find('bn: {')
en_start = js_text.find('en: {')
bn_block = js_text[bn_start:en_start]

diffs = []
for tag, key, inner in tags:
    clean_inner = re.sub(r'<[^>]+>', '', inner).strip()
    clean_inner = re.sub(r'\s+', ' ', clean_inner)
    
    # search key in bn_block: key: "value" or key: 'value'
    pattern = r'^\s*' + re.escape(key) + r'\s*:\s*(?:\"([^\"]*)\"|\'([^\']*)\')'
    m = re.search(pattern, bn_block, re.MULTILINE)
    if m:
        js_val = m.group(1) if m.group(1) is not None else m.group(2)
        js_val = re.sub(r'\s+', ' ', js_val).strip()
        if clean_inner and js_val and clean_inner != js_val:
            diffs.append((key, clean_inner, js_val))
    else:
        diffs.append((key, clean_inner, 'NOT_FOUND_IN_JS'))

with open('mismatches.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total discrepancies: {len(diffs)}\n\n")
    for k, html_v, js_v in diffs:
        out.write(f"KEY: {k}\n")
        out.write(f"  INDEX.PHP: {html_v}\n")
        out.write(f"  I18N_SITE: {js_v}\n")
        out.write("-" * 60 + "\n")

print(f"Done. Found {len(diffs)} discrepancies. Written to mismatches.txt")
