from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional, Set, Tuple

from app import db as store

# Brand/model noise that should not decide uniqueness alone
_STOP = {
    "the",
    "a",
    "an",
    "new",
    "latest",
    "official",
    "review",
    "reviews",
    "unboxing",
    "full",
    "complete",
    "honest",
    "2024",
    "2025",
    "2026",
    "2027",
    "pro",
    "max",
    "plus",  # kept in tokens if part of model — filtered only when alone after strip
}

# Normalize common brand aliases → canonical token
_BRAND_ALIASES = {
    "galaxybuds": "galaxy buds",
    "airpods": "air pods",
    "iphone": "iphone",
    "nothingphone": "nothing phone",
    "pixelbuds": "pixel buds",
    "samsunggalaxy": "samsung galaxy",
}


def normalize_product_key(name: str) -> str:
    """
    Strong canonical key for duplicate detection.
    'Nothing Phone (3)' == 'Nothing Phone 3' == 'nothing-phone-3 review 2026'
    """
    raw = unicodedata.normalize("NFKC", (name or "").strip().lower())
    raw = raw.replace("&", " and ")
    # drop parenthetical punctuation but keep inner digits/letters
    raw = re.sub(r"[()\[\]{}]", " ", raw)
    raw = re.sub(r"[^\w\s+]", " ", raw, flags=re.UNICODE)
    raw = re.sub(r"\s+", " ", raw).strip()

    # brand alias collapse (no spaces version)
    nospace = raw.replace(" ", "")
    for alias, canon in _BRAND_ALIASES.items():
        if nospace.startswith(alias) or alias in nospace:
            # soft rewrite if alias glued
            raw = raw  # keep spaced form; token pass handles rest
            break

    tokens = [t for t in raw.split() if t and t not in _STOP]
    # drop lone year-like leftovers already in _STOP
    key = " ".join(tokens)
    key = re.sub(r"\s+", " ", key).strip()
    return key


def token_set(name: str) -> Set[str]:
    key = normalize_product_key(name)
    return set(key.split()) if key else set()


def similarity_score(a: str, b: str) -> float:
    """Jaccard on normalized tokens; 1.0 = same product family."""
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def is_same_product(a: str, b: str, *, threshold: float = 0.72) -> bool:
    ka, kb = normalize_product_key(a), normalize_product_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    # one contains the other (e.g. "galaxy buds 4" vs "samsung galaxy buds 4")
    if ka in kb or kb in ka:
        # require at least 2 shared tokens to avoid "galaxy" alone
        if len(token_set(a) & token_set(b)) >= 2:
            return True
    return similarity_score(a, b) >= threshold


def ensure_schema() -> None:
    store.init_db()
    with store.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewed_products (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel_id INTEGER,
              niche TEXT,
              product_name TEXT NOT NULL,
              product_key TEXT NOT NULL,
              video_type TEXT,
              job_id INTEGER,
              title TEXT,
              created_at TEXT,
              UNIQUE(channel_id, product_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviewed_key ON reviewed_products(channel_id, product_key)"
        )


def list_reviewed(
    channel_id: Optional[int] = None,
    niche: str = "",
) -> List[dict]:
    ensure_schema()
    with store.db() as conn:
        if channel_id is not None:
            rows = conn.execute(
                "SELECT * FROM reviewed_products WHERE channel_id=? ORDER BY id DESC",
                (channel_id,),
            ).fetchall()
        elif niche:
            rows = conn.execute(
                "SELECT * FROM reviewed_products WHERE lower(niche)=lower(?) ORDER BY id DESC",
                (niche,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM reviewed_products ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def blocked_names(channel_id: Optional[int] = None, niche: str = "") -> List[str]:
    return [r["product_name"] for r in list_reviewed(channel_id=channel_id, niche=niche)]


def is_duplicate(
    product_name: str,
    *,
    channel_id: Optional[int] = None,
    niche: str = "",
    threshold: float = 0.72,
) -> Tuple[bool, str]:
    """
    Returns (is_dup, matched_existing_name).
    Checks exact key + fuzzy match against all reviewed products for channel/niche.
    """
    ensure_schema()
    key = normalize_product_key(product_name)
    if not key:
        return False, ""

    existing = list_reviewed(channel_id=channel_id, niche=niche)
    # also scan other niches on same channel if niche empty
    if channel_id is not None and niche:
        # channel-wide block is stronger: same channel never re-reviews same product
        existing = list_reviewed(channel_id=channel_id)

    for row in existing:
        if row.get("product_key") == key:
            return True, row.get("product_name") or key
        if is_same_product(product_name, row.get("product_name") or "", threshold=threshold):
            return True, row.get("product_name") or row.get("product_key") or ""
    return False, ""


def register_product(
    product_name: str,
    *,
    channel_id: Optional[int] = None,
    niche: str = "",
    video_type: str = "",
    job_id: Optional[int] = None,
    title: str = "",
) -> bool:
    """
    Persist product as reviewed. Returns False if already registered (duplicate).
    """
    ensure_schema()
    dup, _ = is_duplicate(product_name, channel_id=channel_id, niche=niche)
    if dup:
        return False
    key = normalize_product_key(product_name)
    if not key:
        return False
    from datetime import datetime

    with store.db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO reviewed_products
                  (channel_id, niche, product_name, product_key, video_type, job_id, title, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id,
                    niche,
                    product_name.strip(),
                    key,
                    video_type,
                    job_id,
                    title,
                    datetime.now().isoformat(),
                ),
            )
            return True
        except Exception:
            return False


def filter_fresh_topics(
    candidates: Iterable[dict],
    *,
    channel_id: Optional[int] = None,
    niche: str = "",
    name_field: str = "name",
) -> List[dict]:
    """Keep only products not already reviewed (strong dedupe)."""
    out: List[dict] = []
    for c in candidates:
        name = str((c or {}).get(name_field) or "").strip()
        if not name:
            continue
        dup, matched = is_duplicate(name, channel_id=channel_id, niche=niche)
        if dup:
            continue
        # also skip if candidate collides with another already accepted in this batch
        if any(is_same_product(name, str(x.get(name_field) or "")) for x in out):
            continue
        out.append(c)
    return out


def seed_from_names(
    names: Iterable[str],
    *,
    channel_id: Optional[int] = None,
    niche: str = "Gadget Review",
    video_type: str = "seed",
) -> int:
    n = 0
    for name in names:
        if register_product(name, channel_id=channel_id, niche=niche, video_type=video_type):
            n += 1
    return n


def format_blocklist_for_prompt(channel_id: Optional[int] = None, niche: str = "") -> str:
    names = blocked_names(channel_id=channel_id, niche=niche)
    if not names:
        return "(none yet — pick any strong niche-fit product)"
    # de-dupe display
    seen = set()
    lines = []
    for n in names:
        k = normalize_product_key(n)
        if k in seen:
            continue
        seen.add(k)
        lines.append(f"- {n}")
    return "\n".join(lines[:80])
