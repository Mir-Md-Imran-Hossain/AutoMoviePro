"""Canonical Output layout + unique asset IDs (title / language / shot).

Target tree (canonical customer-facing package)::

    Output/
      Short|Long/
        {NN}_{TitleSlug}/
          English/
            Final/{video_uid}_Final_English.mp4
            Video_Clip/{video_uid}_S01_English.mp4
            Audio_Clip/{video_uid}_S01_English.m4a
            Image/{video_uid}_S01_English.jpg
            Script/{video_uid}_Script_English.txt
            Script/{video_uid}_Subtitles_English.srt
          Bangla/
            ...
          Shared/
            Topic.txt
            Dialogue_Plan.json
            Visual_Beat_Plan.json
            Creative_Plan.json
            ...
          _meta/
            Package_Metadata.json
            LINEAGE_INVENTORY.json
            ASSET_ID_MAP.json

``video_uid`` encodes series number + kind + title slug so a single image
filename alone identifies which video and which shot it belongs to.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import ROOT
from pipeline.lang_config import LANG_FOLDERS, folder_for_lang

# Match existing curated packages under Output/ (capital O)
CURATED_OUTPUT_ROOT = ROOT / "Output"

ROLE_DIRS = (
    "Final",
    "Video_Clip",
    "Audio_Clip",
    "Image",
    "Script",
)


def slugify_title(title: str, *, max_len: int = 72) -> str:
    raw = (title or "").strip()
    # Drop common filler words for shorter folder names
    raw = re.sub(r"[\"'`]", "", raw)
    raw = re.sub(r"[^\w\s\-]+", " ", raw, flags=re.UNICODE)
    parts = [p for p in raw.replace("-", " ").split() if p]
    stop = {"a", "an", "the", "of", "for", "and", "to", "in", "on", "with"}
    kept = [p for p in parts if p.lower() not in stop] or parts
    slug = "_".join(kept)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "Untitled"
    # ASCII-ish fold for Windows path safety (keep unicode letters if present)
    safe = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in slug)
    safe = re.sub(r"_+", "_", safe).strip("_") or "Untitled"
    return safe[:max_len]


def kind_label(video_type: str) -> str:
    return "Long" if str(video_type or "").lower() in ("long", "landscape") else "Short"


def kind_folder(video_type: str) -> str:
    return kind_label(video_type)


def lang_folder(code_or_name: str) -> str:
    raw = (code_or_name or "en").strip()
    if raw in LANG_FOLDERS.values():
        return raw
    return folder_for_lang(raw.lower()[:2] if len(raw) <= 3 else raw)


def lang_code(code_or_name: str) -> str:
    raw = (code_or_name or "en").strip()
    inv = {v.lower(): k for k, v in LANG_FOLDERS.items()}
    if raw.lower() in inv:
        return inv[raw.lower()]
    return raw.lower()[:2] or "en"


def scene_token(scene_index: int, *, one_based: bool = True) -> str:
    """Format shot id. ``scene_index`` is 0-based when ``one_based=True`` (S01…)."""
    n = int(scene_index)
    if one_based:
        n = n + 1
    return f"S{max(0, n):02d}"


def find_existing_package_by_slug(
    title: str,
    video_type: str = "short",
    *,
    root: Optional[Path] = None,
) -> Optional[str]:
    """Return existing ``{NN}_{slug}`` folder name if title already packaged."""
    slug = slugify_title(title)
    base = Path(root or CURATED_OUTPUT_ROOT) / kind_folder(video_type)
    if not base.is_dir():
        return None
    # Exact slug match preferred
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        m = re.match(r"^(\d{2,})_(.+)$", p.name)
        if m and m.group(2) == slug:
            return p.name
    # Fallback: folder ends with slug
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name.endswith("_" + slug):
            return p.name
    return None


def next_series_number(video_type: str = "short", *, root: Optional[Path] = None) -> str:
    """Next NN under Output/Short|Long (01, 02, …)."""
    base = Path(root or CURATED_OUTPUT_ROOT) / kind_folder(video_type)
    base.mkdir(parents=True, exist_ok=True)
    used: set[int] = set()
    for p in base.iterdir():
        if not p.is_dir():
            continue
        m = re.match(r"^(\d{2,})_", p.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{n:02d}"


def title_hash(title: str, *, n: int = 8) -> str:
    h = hashlib.sha256((title or "").strip().lower().encode("utf-8")).hexdigest()
    return h[:n].upper()


@dataclass
class VideoIdentity:
    """Stable identity for one produced video (all languages share this)."""

    series: str  # "04"
    kind: str  # "Short" | "Long"
    title: str
    title_slug: str
    video_uid: str  # "04_Short_JWST_Hexagonal_Mirrors_Deep_Field"
    title_hash: str
    video_type: str  # short|long
    folder_name: str  # "04_JWST_Hexagonal_Mirrors_Deep_Field"
    package_root: str  # absolute path string

    def asset_uid(
        self,
        *,
        role: str,
        scene: Optional[int] = None,
        lang: str = "en",
        one_based_scene: bool = True,
    ) -> str:
        """Unique id string for one asset file (without extension)."""
        lang_l = lang_folder(lang)
        role_l = (role or "asset").strip()
        if scene is None:
            return f"{self.video_uid}_{role_l}_{lang_l}"
        shot = scene_token(int(scene), one_based=one_based_scene)
        return f"{self.video_uid}_{shot}_{lang_l}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_video_identity(
    *,
    title: str,
    video_type: str = "short",
    series: Optional[str] = None,
    root: Optional[Path] = None,
    existing_folder: Optional[str] = None,
) -> VideoIdentity:
    slug = slugify_title(title)
    kind = kind_label(video_type)
    existing = existing_folder or find_existing_package_by_slug(title, video_type, root=root)
    ser = (series or "").strip()
    if existing:
        m = re.match(r"^(\d{2,})_(.+)$", existing)
        if m:
            ser = m.group(1)
            slug = m.group(2)
    if not ser:
        ser = next_series_number(video_type, root=root)
    folder = f"{ser}_{slug}"
    uid = f"{ser}_{kind}_{slug}"
    root_p = Path(root or CURATED_OUTPUT_ROOT) / kind / folder
    return VideoIdentity(
        series=ser,
        kind=kind,
        title=(title or slug).strip(),
        title_slug=slug,
        video_uid=uid,
        title_hash=title_hash(title or slug),
        video_type="long" if kind == "Long" else "short",
        folder_name=folder,
        package_root=str(root_p.resolve()),
    )


@dataclass
class PackagePaths:
    identity: VideoIdentity
    root: Path
    shared: Path
    meta: Path
    languages: Dict[str, Path] = field(default_factory=dict)

    def lang_root(self, lang: str) -> Path:
        name = lang_folder(lang)
        p = self.root / name
        self.languages[name] = p
        return p

    def role_dir(self, lang: str, role: str) -> Path:
        role_name = {
            "final": "Final",
            "video": "Video_Clip",
            "video_clip": "Video_Clip",
            "audio": "Audio_Clip",
            "audio_clip": "Audio_Clip",
            "image": "Image",
            "script": "Script",
        }.get((role or "").lower(), role)
        d = self.lang_root(lang) / role_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def asset_path(
        self,
        *,
        lang: str,
        role: str,
        ext: str,
        scene: Optional[int] = None,
        one_based_scene: bool = True,
        suffix_tag: str = "",
    ) -> Path:
        """Build full path for an asset with unique title-based filename."""
        ext = ext if ext.startswith(".") else f".{ext}"
        role_key = {
            "final": "Final",
            "video": "Video_Clip",
            "video_clip": "Video_Clip",
            "audio": "Audio_Clip",
            "audio_clip": "Audio_Clip",
            "image": "Image",
            "script": "Script",
            "subtitle": "Script",
            "dialogue": "Script",
            "topic": "Script",
        }.get((role or "").lower(), "Script")
        uid = self.identity.asset_uid(
            role=role_key if scene is None and role_key == "Final" else (
                "Final" if role_key == "Final" else "Asset"
            ),
            scene=scene,
            lang=lang,
            one_based_scene=one_based_scene,
        )
        # Refine naming for clarity
        lang_l = lang_folder(lang)
        if role_key == "Final":
            name = f"{self.identity.video_uid}_Final_{lang_l}{suffix_tag}{ext}"
        elif scene is not None:
            shot = scene_token(int(scene), one_based=one_based_scene)
            name = f"{self.identity.video_uid}_{shot}_{lang_l}{suffix_tag}{ext}"
        else:
            tag = (role or "Asset").replace(" ", "_")
            name = f"{self.identity.video_uid}_{tag}_{lang_l}{suffix_tag}{ext}"
        dest = self.role_dir(lang, role_key) / name
        return dest


def ensure_package_dirs(identity: VideoIdentity, languages: Optional[List[str]] = None) -> PackagePaths:
    root = Path(identity.package_root)
    shared = root / "Shared"
    meta = root / "_meta"
    for d in (root, shared, meta):
        d.mkdir(parents=True, exist_ok=True)
    paths = PackagePaths(identity=identity, root=root, shared=shared, meta=meta)
    langs = languages or ["en"]
    for code in langs:
        lr = paths.lang_root(code)
        for role in ROLE_DIRS:
            (lr / role).mkdir(parents=True, exist_ok=True)
    return paths


def parse_asset_filename(name: str) -> Dict[str, Any]:
    """Decode title/shot/lang from a curated filename (best-effort)."""
    stem = Path(name).stem
    # 04_Short_Title_S01_English  OR  04_Short_Title_Final_English
    m = re.match(
        r"^(?P<series>\d{2,})_(?P<kind>Short|Long)_(?P<title>.+?)_(?:(?P<shot>S\d{2})|(?P<final>Final))_(?P<lang>[A-Za-z]+)$",
        stem,
    )
    if not m:
        return {"ok": False, "filename": name}
    return {
        "ok": True,
        "series": m.group("series"),
        "kind": m.group("kind"),
        "title_slug": m.group("title"),
        "shot": m.group("shot"),
        "is_final": bool(m.group("final")),
        "language": m.group("lang"),
        "video_uid": f"{m.group('series')}_{m.group('kind')}_{m.group('title')}",
        "filename": name,
    }


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
