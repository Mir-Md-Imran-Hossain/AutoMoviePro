"""Custom-pipeline package layout (user-specified Output tree).

Output/
  Short|Long/
    001_(Topic Name)/
      Audio/{BN,EN,HI,UR,TL,ML}/
      Image/
      File/          ← all JSON (Script/Visual/Voice titled files)
      Video/
        Video Clips/
        Final Video/{BN,EN,HI,UR,TL,ML}/
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from app.config import ROOT
from pipeline.output_layout import CURATED_OUTPUT_ROOT, kind_folder, write_json

# Windows-forbidden filename chars
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# User-facing language folder codes under Audio / Final Video
LANG_AUDIO_CODES = ("BN", "EN", "HI", "UR", "TL", "ML")

LANG_NAME_TO_CODE: Dict[str, str] = {
    "bangla": "BN",
    "bengali": "BN",
    "bn": "BN",
    "english": "EN",
    "en": "EN",
    "hindi": "HI",
    "hi": "HI",
    "urdu": "UR",
    "ur": "UR",
    "tamil": "TL",  # user format uses TL (not TA)
    "ta": "TL",
    "tl": "TL",
    "malayalam": "ML",
    "ml": "ML",
}

CODE_TO_LANG_NAME: Dict[str, str] = {
    "BN": "Bangla",
    "EN": "English",
    "HI": "Hindi",
    "UR": "Urdu",
    "TL": "Tamil",
    "ML": "Malayalam",
}

# Internal 2-letter codes used by TTS contracts / legacy helpers
CODE_TO_ISO: Dict[str, str] = {
    "BN": "bn",
    "EN": "en",
    "HI": "hi",
    "UR": "ur",
    "TL": "ta",
    "ML": "ml",
}


def sanitize_topic_title(title: str, *, max_len: int = 100) -> str:
    """Keep Bangla/Unicode letters — strip Windows-illegal + emoji (breaks ffmpeg paths)."""
    import re

    raw = str(title or "").strip() or "Untitled"
    raw = _BAD_CHARS.sub("", raw)
    # Drop emoji / symbols that break ffmpeg concat & some Windows tools
    raw = re.sub(
        r"[\U00010000-\U0010ffff\u2600-\u27BF\uFE0F\u200D\uFE0E]",
        "",
        raw,
    )
    raw = re.sub(r"[🔥✨😱🚀💡🎯⭐️❤♥★☆▪▫•·|]+", "", raw)
    # Apostrophes/quotes break ffmpeg subtitles='…' filter quoting
    raw = raw.replace("'", "").replace('"', "").replace("`", "").replace("’", "").replace("‘", "")
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = raw.rstrip(" .")
    if len(raw) > max_len:
        raw = raw[: max_len - 1].rstrip() + "…"
    return raw or "Untitled"


def package_folder_name(number: str | int, title: str) -> str:
    """001_(Topic Name) — spaces kept, NO per-letter underscores."""
    num = f"{int(number):03d}" if str(number).isdigit() else str(number).zfill(3)
    safe = sanitize_topic_title(title)
    return f"{num}_({safe})"


def lang_code_for(language: str) -> str:
    key = (language or "").strip().lower()
    if key.upper() in LANG_AUDIO_CODES:
        return key.upper()
    return LANG_NAME_TO_CODE.get(key, "EN")


def iso_code_for(language: str) -> str:
    return CODE_TO_ISO.get(lang_code_for(language), "en")


def next_package_number(kind_dir: Path) -> str:
    kind_dir.mkdir(parents=True, exist_ok=True)
    used = set()
    for p in kind_dir.iterdir():
        if not p.is_dir():
            continue
        m = re.match(r"^(\d{2,3})_", p.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{n:03d}"


@dataclass
class CustomPackagePaths:
    root: Path
    number: str
    title: str
    video_type: str  # short|long
    folder_name: str

    @property
    def audio(self) -> Path:
        return self.root / "Audio"

    @property
    def image(self) -> Path:
        return self.root / "Image"

    @property
    def file_dir(self) -> Path:
        return self.root / "File"

    @property
    def video(self) -> Path:
        return self.root / "Video"

    @property
    def video_clips(self) -> Path:
        return self.video / "Video Clips"

    @property
    def final_video(self) -> Path:
        return self.video / "Final Video"

    @property
    def thumbnail(self) -> Path:
        return self.root / "Thumbnail"

    def audio_lang(self, language: str) -> Path:
        code = lang_code_for(language)
        d = self.audio / code
        d.mkdir(parents=True, exist_ok=True)
        return d

    def final_video_lang(self, language: str) -> Path:
        code = lang_code_for(language)
        d = self.final_video / code
        d.mkdir(parents=True, exist_ok=True)
        return d

    def thumbnail_lang(self, language: str) -> Path:
        code = lang_code_for(language)
        d = self.thumbnail / code
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_tree(self) -> "CustomPackagePaths":
        self.root.mkdir(parents=True, exist_ok=True)
        self.audio.mkdir(parents=True, exist_ok=True)
        self.image.mkdir(parents=True, exist_ok=True)
        self.file_dir.mkdir(parents=True, exist_ok=True)
        self.video_clips.mkdir(parents=True, exist_ok=True)
        self.final_video.mkdir(parents=True, exist_ok=True)
        self.thumbnail.mkdir(parents=True, exist_ok=True)
        for code in LANG_AUDIO_CODES:
            (self.audio / code).mkdir(parents=True, exist_ok=True)
            (self.final_video / code).mkdir(parents=True, exist_ok=True)
            (self.thumbnail / code).mkdir(parents=True, exist_ok=True)
        return self


def create_package(
    *,
    title: str,
    video_type: str = "short",
    output_root: Optional[Path] = None,
    number: Optional[str] = None,
) -> CustomPackagePaths:
    kind = kind_folder(video_type)
    base = Path(output_root or CURATED_OUTPUT_ROOT) / kind
    base.mkdir(parents=True, exist_ok=True)
    num = (number or "").strip() or next_package_number(base)
    if num.isdigit():
        num = f"{int(num):03d}"
    folder = package_folder_name(num, title)
    root = base / folder
    paths = CustomPackagePaths(
        root=root,
        number=num,
        title=sanitize_topic_title(title),
        video_type="long" if kind == "Long" else "short",
        folder_name=folder,
    )
    return paths.ensure_tree()


def open_package(package_root: Path | str) -> CustomPackagePaths:
    root = Path(package_root)
    m = re.match(r"^(\d{2,3})_\((.+)\)$", root.name)
    if m:
        num, title = m.group(1), m.group(2)
    else:
        # legacy fallback: 10_slug or 001_slug
        m2 = re.match(r"^(\d{2,3})_(.+)$", root.name)
        num = m2.group(1) if m2 else "001"
        title = m2.group(2).replace("_", " ") if m2 else root.name
    kind = root.parent.name
    paths = CustomPackagePaths(
        root=root,
        number=f"{int(num):03d}" if str(num).isdigit() else str(num),
        title=sanitize_topic_title(title),
        video_type="long" if kind == "Long" else "short",
        folder_name=root.name,
    )
    return paths.ensure_tree()


def titled_json_name(kind: str, number: str, title: str, *, lang: str = "") -> str:
    """Script_001_(Title).json / Voice_001_EN_(Title).json"""
    safe = sanitize_topic_title(title)
    num = f"{int(number):03d}" if str(number).isdigit() else str(number)
    if lang:
        return f"{kind}_{num}_{lang.upper()}_({safe}).json"
    return f"{kind}_{num}_({safe}).json"


def titled_thumbnail_name(number: str, title: str, *, lang: str = "EN", ext: str = "jpg") -> str:
    """Thumbnail_001_EN_(Title).jpg / Thumbnail_001_BN_(Title).png"""
    safe = sanitize_topic_title(title)
    num = f"{int(number):03d}" if str(number).isdigit() else str(number)
    code = (lang or "EN").upper()
    extension = ext.lstrip(".")
    return f"Thumbnail_{num}_{code}_({safe}).{extension}"


def write_file_json(paths: CustomPackagePaths, filename: str, payload: object) -> Path:
    paths.file_dir.mkdir(parents=True, exist_ok=True)
    out = paths.file_dir / filename
    write_json(out, payload)
    return out
