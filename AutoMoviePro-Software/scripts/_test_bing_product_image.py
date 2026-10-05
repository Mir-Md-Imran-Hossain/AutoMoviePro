from __future__ import annotations

import html as html_lib
import re
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v4" / "_bing_oneplus.jpg"


def main() -> None:
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    q = "OnePlus 13 product"
    url = f"https://www.bing.com/images/search?q={quote(q)}"
    r = httpx.get(url, headers={"User-Agent": ua}, timeout=40, follow_redirects=True)
    text = html_lib.unescape(r.text)
    print("bing", r.status_code, len(text))

    murls = re.findall(r'"murl"\s*:\s*"(https?://[^"]+)"', text)
    murls += re.findall(r"murl&quot;:&quot;(https?://[^&]+)&quot;", r.text)
    murls = [html_lib.unescape(u).replace("\\/", "/") for u in murls]
    print("murls", len(murls))

    scored = []
    for u in murls:
        ul = u.lower()
        score = 0
        if "oneplus" in ul or "opstatics" in ul or "oxygen" in ul:
            score += 6
        if "13" in ul:
            score += 2
        if any(ul.endswith(ext) or ext in ul for ext in (".jpg", ".jpeg", ".png", ".webp")):
            score += 1
        if any(bad in ul for bad in ("logo", "icon", "sprite", "favicon", "launcher")):
            score -= 4
        scored.append((score, u))
    scored.sort(key=lambda x: x[0], reverse=True)
    for s, u in scored[:12]:
        print(s, u[:130])

    best = next((u for s, u in scored if s >= 6), None)
    if not best:
        raise SystemExit("no product url")
    img = httpx.get(
        best,
        headers={"User-Agent": ua, "Referer": "https://www.bing.com/"},
        timeout=40,
        follow_redirects=True,
    )
    ctype = img.headers.get("content-type", "")
    print("fetch", img.status_code, ctype, len(img.content))
    if "image" not in ctype or len(img.content) < 5000:
        raise SystemExit("not an image")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(img.content)
    print("saved", OUT)


if __name__ == "__main__":
    main()
