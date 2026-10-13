"""Canvas-aware subtitle burn styles — keep captions readable, not full-screen.

ASS FontSize without PlayRes scales badly on 9:16 (1080x1920). We always
declare PlayResX/PlayResY matching the output canvas and use outline (not
opaque BorderStyle=3 boxes). Max ~2 short lines per cue.
"""
from __future__ import annotations

import os
import re
import unicodedata
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import uharfbuzz as hb
    import freetype
    from PIL import Image, ImageFilter
    import numpy as np
    HAVE_HARFBUZZ = True
except ImportError:
    HAVE_HARFBUZZ = False

COMPLEX_LANGS = {"bn", "as", "hi", "mr", "ne", "ta", "te", "ml", "kn", "gu", "pa", "or", "ur", "ar", "fa"}


def is_complex_script(lang: str) -> bool:
    return (lang or "en").lower()[:2] in COMPLEX_LANGS


def parse_canvas(size: str | None) -> Tuple[int, int]:
    raw = str(size or "1080x1920").lower().replace("*", "x")
    try:
        w, h = raw.split("x", 1)
        return max(320, int(float(w))), max(320, int(float(h)))
    except Exception:
        return 1080, 1920


def preferred_font(lang: str = "en") -> str:
    lang = (lang or "en").lower()[:2]
    font_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    # Windows & bundled fonts that handle Indic / Arabic / Bengali shaping with 100% conjunct fidelity
    if lang in ("bn", "as"):
        if (font_dir / "Kalpurush.ttf").exists():
            return "Kalpurush"
        if (font_dir / "PotroSansBangla-Bold.ttf").exists():
            return "Potro Sans Bangla"
        if (font_dir / "vrindab.ttf").exists():
            return "Vrinda"
        return "Nirmala UI"
    if lang in ("hi", "mr", "ne"):
        return "Nirmala UI"
    if lang in ("te", "ta", "ml", "kn"):
        return "Nirmala UI"
    if lang in ("ur", "ar", "fa", "he"):
        return "Segoe UI"
    return "Arial"


def get_fonts_dir() -> str:
    """Returns absolute path to bundled fonts for FFmpeg fontsdir parameter."""
    p = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    return str(p).replace("\\", "/")


def font_size_for_canvas(width: int, height: int, is_short: bool | None = None) -> int:
    """Font size scaled for canvas: prominent, bold and ultra-legible across mobile and desktop.
    
    Shorts (9:16 - 1080x1920): 76–86pt (scaled for arm's length mobile readability).
    Long (16:9 - 1920x1080): 52–64pt (bold, clearly visible on desktop/TV).
    """
    short = min(width, height)
    if is_short is None:
        is_short = (height > width)
    if is_short:
        # Vertical shorts (9:16): responsive mobile styling, slightly smaller to prevent layout breaking
        return max(64, min(80, int(short * 0.065)))
    # Horizontal widescreen (16:9): clean, cinematic, highly readable
    return max(50, min(64, int(short * 0.052)))


def margin_v_for_canvas(height: int, is_short: bool | None = None) -> int:
    """Lift captions safely above platform UI (TikTok / Reels / Shorts bottom bar)."""
    if is_short is None:
        is_short = (height > 1200)
    if is_short:
        # Vertical 9:16: safe zone well above sound track, handle, and caption bar
        return max(240, min(320, int(height * 0.14)))
    return max(64, min(140, int(height * 0.075)))


def ass_force_style(*, size: str = "1080x1920", lang: str = "en", is_short: bool | None = None) -> str:
    """ffmpeg subtitles filter force_style string (no outer quotes)."""
    w, h = parse_canvas(size)
    if is_short is None:
        is_short = (h > w)
    fs = font_size_for_canvas(w, h, is_short=is_short)
    mv = margin_v_for_canvas(h, is_short=is_short)
    font = preferred_font(lang)
    if is_short:
        # High-impact short-form styling: Bold yellow, thick black outline, platform safe margins
        # MarginR=80 avoids TikTok / Reels / Shorts right-side action buttons
        return (
            f"FontName={font},FontSize={fs},PrimaryColour=&H0000FFFF&,"
            f"OutlineColour=&H00000000&,BackColour=&H80000000&,"
            f"BorderStyle=1,Outline=4.2,Shadow=2.0,Alignment=2,"
            f"MarginL=60,MarginR=80,MarginV={mv},Bold=1,ScaleX=100,ScaleY=100"
        )
    return (
        f"FontName={font},FontSize={fs},PrimaryColour=&H00FFFFFF&,"
        f"OutlineColour=&H00000000&,BackColour=&H80000000&,"
        f"BorderStyle=1,Outline=3.2,Shadow=1.5,Alignment=2,"
        f"MarginL=48,MarginR=48,MarginV={mv},Bold=1,ScaleX=100,ScaleY=100"
    )


def wrap_cue_text(text: str, *, max_chars_per_line: int = 28, max_lines: int = 2) -> str:
    """Hard-wrap a single cue into ≤2 short lines for vertical screens."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return " "
    try:
        from pipeline.localization_consistency.subtitle_rules import suggest_semantic_line_break

        broken = suggest_semantic_line_break(t, max_chars_per_line=max_chars_per_line)
        lines = [ln.strip() for ln in broken.splitlines() if ln.strip()]
    except Exception:
        lines = [t]
    if len(lines) == 1 and len(lines[0]) > max_chars_per_line:
        words = lines[0].split()
        mid = max(1, len(words) // 2)
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    lines = lines[:max_lines]
    # Soft-trim runaway lines
    out = []
    for ln in lines:
        if len(ln) > max_chars_per_line + 10:
            parts = ln.split()
            keep: List[str] = []
            for w in parts:
                trial = (" ".join(keep + [w])).strip()
                if len(trial) > max_chars_per_line + 6 and keep:
                    break
                keep.append(w)
            ln = " ".join(keep) if keep else ln[: max_chars_per_line + 6]
        out.append(ln)
    return "\n".join(out) if out else t[:max_chars_per_line]


def chunk_words_for_cues(
    text: str,
    *,
    words_per_chunk: int = 6,
    max_chars_per_line: int = 28,
    is_short: bool = False,
) -> List[str]:
    """Split narration into short on-screen cues (industrial caption density)."""
    if is_short and words_per_chunk == 6:
        words_per_chunk = 2
    body = re.sub(r"\s+", " ", (text or "").strip()) or " "
    words = body.split()
    chunks: List[str] = []
    buf: List[str] = []
    for w in words:
        buf.append(w)
        # Prefer punctuation breaks
        punct = w.endswith((".", "?", "!", "।", "؟"))
        if len(buf) >= words_per_chunk or (punct and len(buf) >= 2):
            chunks.append(wrap_cue_text(" ".join(buf), max_chars_per_line=max_chars_per_line))
            buf = []
    if buf:
        chunks.append(wrap_cue_text(" ".join(buf), max_chars_per_line=max_chars_per_line))
    return chunks or [wrap_cue_text(body, max_chars_per_line=max_chars_per_line)]


def _parse_srt_timestamp(ts: str) -> float:
    """Parse SRT timestamp (00:00:01,200) into seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def _format_ass_timestamp(sec: float) -> str:
    """Format seconds into ASS timestamp (0:00:01.20)."""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_to_styled_ass(
    srt_path: Path,
    ass_path: Path,
    *,
    size: str = "1080x1920",
    lang: str = "en",
    is_short: bool | None = None,
) -> Path:
    """Convert SRT → ASS with explicit PlayRes and dynamic short-form chunking."""
    w, h = parse_canvas(size)
    if is_short is None:
        is_short = (h > w)
    fs = font_size_for_canvas(w, h, is_short=is_short)
    mv = margin_v_for_canvas(h, is_short=is_short)
    font = preferred_font(lang)
    raw = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", raw.strip())
    events: List[str] = []

    def _ts_ass(ts: str) -> str:
        # SRT 00:00:01,200 → ASS 0:00:01.20
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) != 3:
            return "0:00:00.00"
        h0, m0, rest = parts
        if "." in rest:
            s0, ms = rest.split(".", 1)
            cs = int(float("0." + ms[:3].ljust(3, "0")) * 100)
        else:
            s0, cs = rest, 0
        return f"{int(h0)}:{int(m0):02d}:{int(s0):02d}.{cs:02d}"

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # skip index line if present
        if "-->" not in lines[0] and len(lines) >= 2 and "-->" in lines[1]:
            lines = lines[1:]
        if "-->" not in lines[0]:
            continue
        timing = lines[0]
        try:
            a, b = [x.strip() for x in timing.split("-->")]
        except Exception:
            continue

        import unicodedata
        cue_raw = unicodedata.normalize("NFC", " ".join(lines[1:]).strip())
        if not cue_raw:
            continue

        if is_short:
            words = cue_raw.split()
            if len(words) > 3:
                # Dynamic short-form sub-chunking: break into punchy 1-3 word cues
                t0 = _parse_srt_timestamp(a)
                t1 = _parse_srt_timestamp(b)
                dur = max(0.2, t1 - t0)

                sub_chunks: List[str] = []
                wi = 0
                while wi < len(words):
                    rem = len(words) - wi
                    if rem == 4:
                        take = 2
                    elif rem == 1 and sub_chunks:
                        sub_chunks[-1] += " " + words[wi]
                        break
                    else:
                        take = min(2, rem)
                    sub_chunks.append(" ".join(words[wi : wi + take]))
                    wi += take

                total_chars = max(1, sum(len(c) for c in sub_chunks))
                cur_t = t0
                for c_idx, s_text in enumerate(sub_chunks):
                    frac = len(s_text) / total_chars
                    span = max(0.25, dur * frac)
                    next_t = min(t1, cur_t + span) if c_idx < len(sub_chunks) - 1 else t1
                    if next_t <= cur_t:
                        next_t = min(t1, cur_t + 0.25)
                    rendered = wrap_cue_text(s_text, max_chars_per_line=20).replace("\n", r"\N")
                    events.append(f"Dialogue: 0,{_format_ass_timestamp(cur_t)},{_format_ass_timestamp(next_t)},Default,,0,0,0,,{rendered}")
                    cur_t = next_t
                continue

        text = wrap_cue_text(cue_raw, max_chars_per_line=22 if is_short else 42)
        text = text.replace("\n", r"\N")
        events.append(f"Dialogue: 0,{_ts_ass(a)},{_ts_ass(b)},Default,,0,0,0,,{text}")

    if is_short:
        # High-impact short-form style: Yellow, thick black outline, platform safe-margin
        style_line = (
            f"Style: Default,{font},{fs},&H0000FFFF,&H000000FF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,3.8,1.8,2,60,80,{mv},1"
        )
    else:
        style_line = (
            f"Style: Default,{font},{fs},&H00FFFFFF,&H000000FF,&H80000000,&H64000000,"
            f"0,0,0,0,100,100,0,0,1,2.2,0.8,2,48,48,{mv},1"
        )

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path = Path(ass_path)
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _parse_ass_timestamp(ts: str) -> float:
    try:
        parts = ts.strip().split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


def parse_sub_to_cues(sub_path: Path) -> List[Dict[str, Any]]:
    """Parse an .srt or .ass subtitle file into a normalized list of cue dicts."""
    sub_path = Path(sub_path)
    if not sub_path.is_file():
        return []
    raw = sub_path.read_text(encoding="utf-8", errors="ignore")
    cues: List[Dict[str, Any]] = []

    if sub_path.suffix.lower() == ".ass":
        for line in raw.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) >= 10:
                    t0 = _parse_ass_timestamp(parts[1])
                    t1 = _parse_ass_timestamp(parts[2])
                    txt = parts[9].replace(r"\N", "\n")
                    txt = re.sub(r"\{.*?\}", "", txt).strip()
                    if txt:
                        cues.append({"start": t0, "end": t1, "text": txt})
    else:  # srt
        blocks = re.split(r"\n\s*\n", raw.strip())
        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if len(lines) >= 2 and "-->" in lines[0]:
                timing = lines[0]
                txt = " ".join(lines[1:])
            elif len(lines) >= 3 and "-->" in lines[1]:
                timing = lines[1]
                txt = " ".join(lines[2:])
            else:
                continue
            try:
                a, b = [x.strip() for x in timing.split("-->")]
                t0 = _parse_srt_timestamp(a)
                t1 = _parse_srt_timestamp(b)
                if txt.strip():
                    cues.append({"start": t0, "end": t1, "text": txt.strip()})
            except Exception:
                continue
    return cues


def resolve_complex_font_path(lang: str) -> Tuple[str, int]:
    """Find a TrueType/OpenType font that supports complex script shaping with HarfBuzz."""
    lang = (lang or "en").lower()[:2]
    bundled = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    win = Path("C:/Windows/Fonts")

    if lang in ("bn", "as"):
        for cand in [bundled / "vrindab.ttf", bundled / "PotroSansBangla-Bold.ttf", bundled / "Kalpurush.ttf", win / "vrindab.ttf"]:
            if cand.exists():
                return str(cand), 0
        if (win / "Nirmala.ttc").exists():
            return str(win / "Nirmala.ttc"), 0

    if lang in ("hi", "mr", "ne", "sa"):
        if (win / "Nirmala.ttc").exists():
            return str(win / "Nirmala.ttc"), 0
        for cand in [bundled / "Nirmala.ttf", bundled / "Mangal.ttf", win / "mangal.ttf"]:
            if cand.exists():
                return str(cand), 0

    if lang in ("ta", "te", "ml", "kn"):
        if (win / "Nirmala.ttc").exists():
            return str(win / "Nirmala.ttc"), 0
        for cand in [bundled / "Nirmala.ttf", win / "Latha.ttf", win / "Gautami.ttf", win / "Kartika.ttf", win / "Raavi.ttf"]:
            if cand.exists():
                return str(cand), 0

    if lang in ("ur", "ar", "fa"):
        for cand in [win / "arial.ttf", win / "segoeui.ttf", win / "times.ttf"]:
            if cand.exists():
                return str(cand), 0

    for cand in [win / "arial.ttf", bundled / "vrindab.ttf"]:
        if cand.exists():
            return str(cand), 0
    return "arial.ttf", 0


def render_harfbuzz_cues_to_overlay(
    cues_or_file: Any,
    *,
    out_dir: Optional[Path] = None,
    size: str = "1080x1920",
    lang: str = "bn",
    is_short: bool | None = None,
) -> Path:
    """Renders subtitle cues to transparent PNGs with FreeType+HarfBuzz, outputting subs_concat.txt for overlay."""
    if not HAVE_HARFBUZZ:
        raise RuntimeError("uharfbuzz, freetype-py, and Pillow are required for complex script rendering.")

    if isinstance(cues_or_file, (str, Path)):
        cues = parse_sub_to_cues(Path(cues_or_file))
    elif isinstance(cues_or_file, list):
        cues = cues_or_file
    else:
        cues = []

    w, h = parse_canvas(size)
    if is_short is None:
        is_short = (h > w)

    fs = font_size_for_canvas(w, h, is_short=is_short)
    mv = margin_v_for_canvas(h, is_short=is_short)

    font_path, font_idx = resolve_complex_font_path(lang)
    face = freetype.Face(font_path, index=font_idx)
    face.set_pixel_sizes(0, fs)

    with open(font_path, "rb") as f:
        font_data = f.read()
    hb_face = hb.Face(font_data, index=font_idx)
    hb_font = hb.Font(hb_face)
    hb_font.scale = (fs * 64, fs * 64)

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="amp_hb_overlay_"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    empty_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    empty_path = out_dir / "cue_empty.png"
    empty_img.save(empty_path)

    line_height = int(fs * 1.22)
    max_c_len = 20 if is_short else 42

    rendered_cues: List[Dict[str, Any]] = []
    sorted_cues = sorted(cues, key=lambda c: float(c.get("start", 0.0)))

    for idx, cue in enumerate(sorted_cues):
        t0 = max(0.0, float(cue.get("start", 0.0)))
        t1 = max(t0 + 0.1, float(cue.get("end", t0 + 1.0)))
        dur = max(0.1, t1 - t0)
        raw_text = str(cue.get("text", "")).strip()
        if not raw_text:
            continue

        wrapped = wrap_cue_text(raw_text, max_chars_per_line=max_c_len)
        lines = [ln.strip() for ln in wrapped.split("\n") if ln.strip()]
        if not lines:
            continue

        total_lines_h = len(lines) * line_height
        start_y = h - mv - total_lines_h

        mask = Image.new("L", (w, h), 0)

        for line_i, line in enumerate(lines):
            buf = hb.Buffer()
            buf.add_str(line)
            buf.guess_segment_properties()
            hb.shape(hb_font, buf)

            infos = buf.glyph_infos
            positions = buf.glyph_positions
            line_w = sum(p.x_advance for p in positions) // 64

            cur_fs = fs
            cur_line_h = line_height
            if line_w > (w - 80):
                scale_ratio = (w - 80) / max(1, line_w)
                cur_fs = max(36, int(fs * scale_ratio))
                cur_line_h = int(cur_fs * 1.22)
                face.set_pixel_sizes(0, cur_fs)
                hb_font.scale = (cur_fs * 64, cur_fs * 64)
                buf = hb.Buffer()
                buf.add_str(line)
                buf.guess_segment_properties()
                hb.shape(hb_font, buf)
                infos = buf.glyph_infos
                positions = buf.glyph_positions
                line_w = sum(p.x_advance for p in positions) // 64
                face.set_pixel_sizes(0, fs)
                hb_font.scale = (fs * 64, fs * 64)

            cur_x = max(20, (w - line_w) // 2)
            cur_y = start_y + (line_i * cur_line_h) + cur_fs

            for info, pos in zip(infos, positions):
                gid = info.codepoint
                face.load_glyph(gid, freetype.FT_LOAD_RENDER)
                slot = face.glyph
                bitmap = slot.bitmap
                bx = cur_x + (pos.x_offset // 64) + slot.bitmap_left
                by = cur_y - (pos.y_offset // 64) - slot.bitmap_top
                bw, bh = bitmap.width, bitmap.rows
                if bw > 0 and bh > 0 and 0 <= bx < w and 0 <= by < h:
                    glyph_arr = np.array(bitmap.buffer, dtype=np.uint8).reshape((bh, bw))
                    glyph_img = Image.fromarray(glyph_arr, "L")
                    mask.paste(glyph_img, (bx, by))
                cur_x += pos.x_advance // 64

        outline_mask = mask.filter(ImageFilter.MaxFilter(11 if is_short else 7))
        shadow_mask = outline_mask.filter(ImageFilter.GaussianBlur(3))

        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(Image.new("RGBA", (w, h), (0, 0, 0, 160)), (2, 3), shadow_mask)
        canvas.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 0), outline_mask)
        fill_color = (255, 235, 59, 255) if is_short else (255, 255, 255, 255)
        canvas.paste(Image.new("RGBA", (w, h), fill_color), (0, 0), mask)

        img_name = f"cue_{idx:03d}.png"
        img_path = out_dir / img_name
        canvas.save(img_path)
        rendered_cues.append({"path": img_name, "start": t0, "end": t1, "dur": dur})

    concat_lines: List[str] = []
    curr_time = 0.0
    for rc in rendered_cues:
        gap = rc["start"] - curr_time
        if gap > 0.04:
            concat_lines.append("file 'cue_empty.png'")
            concat_lines.append(f"duration {gap:.3f}")
            curr_time += gap
        concat_lines.append(f"file '{rc['path']}'")
        concat_lines.append(f"duration {rc['dur']:.3f}")
        curr_time = rc["end"]

    concat_lines.append("file 'cue_empty.png'")
    concat_path = out_dir / "subs_concat.txt"
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    return concat_path


def apply_subtitles_to_vf(
    base_vf: str | Sequence[str] | None,
    cues_or_sub: Any,
    *,
    size: str = "1080x1920",
    lang: str = "en",
    is_short: bool | None = None,
) -> str:
    """Seamlessly burn subtitles into video filtergraph.
    
    For Indic and complex scripts, uses HarfBuzz+FreeType transparent overlay (zero broken conjuncts).
    For Latin/English, uses ASS subtitle filter.
    """
    if isinstance(base_vf, (list, tuple)):
        base_str = ",".join([str(f).strip() for f in base_vf if str(f).strip()])
    else:
        base_str = str(base_vf or "").strip()

    if is_complex_script(lang) and HAVE_HARFBUZZ:
        try:
            concat_file = render_harfbuzz_cues_to_overlay(
                cues_or_sub,
                size=size,
                lang=lang,
                is_short=is_short,
            )
            posix_path = concat_file.resolve().as_posix().replace(":", r"\:")
            if base_str:
                return f"[in]{base_str}[v0]; movie='{posix_path}':f=concat[sub]; [v0][sub]overlay=0:0:shortest=1[out]"
            return f"[in]null[v0]; movie='{posix_path}':f=concat[sub]; [v0][sub]overlay=0:0:shortest=1[out]"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("HarfBuzz subtitle overlay failed (%s), falling back to ASS", exc)

    # Standard ASS fallback path
    if isinstance(cues_or_sub, (str, Path)) and Path(cues_or_sub).is_file():
        burn = burn_subtitles_filter(Path(cues_or_sub), size=size, lang=lang)
    elif isinstance(cues_or_sub, list):
        tmp_dir = Path(tempfile.mkdtemp(prefix="amp_ass_"))
        ass_path = tmp_dir / f"shot_{lang}.ass"
        _write_simple_ass(cues_or_sub, ass_path, size=size, lang=lang, is_short=is_short)
        burn = burn_subtitles_filter(ass_path, size=size, lang=lang)
    else:
        return base_str or "null"

    if base_str:
        return f"{base_str},{burn}"
    return burn


def _write_simple_ass(
    cues: List[Dict[str, Any]],
    ass_path: Path,
    *,
    size: str = "1080x1920",
    lang: str = "en",
    is_short: bool | None = None,
) -> Path:
    w, h = parse_canvas(size)
    if is_short is None:
        is_short = (h > w)
    fs = font_size_for_canvas(w, h, is_short=is_short)
    mv = margin_v_for_canvas(h, is_short=is_short)
    font = preferred_font(lang)

    if is_short:
        style_line = (
            f"Style: Default,{font},{fs},&H0000FFFF,&H000000FF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,3.8,1.8,2,60,80,{mv},1"
        )
    else:
        style_line = (
            f"Style: Default,{font},{fs},&H00FFFFFF,&H000000FF,&H80000000,&H64000000,"
            f"0,0,0,0,100,100,0,0,1,2.2,0.8,2,48,48,{mv},1"
        )

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    max_c_len = 20 if is_short else 42
    for cue in cues:
        t0 = _format_ass_timestamp(float(cue.get("start", 0.0)))
        t1 = _format_ass_timestamp(float(cue.get("end", 1.0)))
        txt = wrap_cue_text(str(cue.get("text", "")), max_chars_per_line=max_c_len).replace("\n", r"\N")
        events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{txt}")

    ass_path = Path(ass_path)
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def burn_subtitles_filter(
    subtitle_file: Path,
    *,
    size: str = "1080x1920",
    lang: str = "en",
) -> str:
    """Return one ffmpeg vf fragment that burns readable captions."""
    sub = Path(subtitle_file)
    if not sub.is_file():
        raise FileNotFoundError(str(sub))

    if is_complex_script(lang) and HAVE_HARFBUZZ:
        try:
            cues = parse_sub_to_cues(sub)
            if cues:
                concat_file = render_harfbuzz_cues_to_overlay(cues, size=size, lang=lang)
                posix_path = concat_file.resolve().as_posix().replace(":", r"\:")
                return f"movie='{posix_path}':f=concat[sub];[in][sub]overlay=0:0:shortest=1"
        except Exception:
            pass

    # Prefer ASS with PlayRes baked in — do NOT also force_style (breaks Indic glyphs)
    if sub.suffix.lower() == ".srt":
        ass = sub.with_suffix(".ass")
        srt_to_styled_ass(sub, ass, size=size, lang=lang)
        sub = ass
    elif sub.suffix.lower() != ".ass":
        sp = str(sub.resolve()).replace("\\", "/").replace(":", "\\:")
        style = ass_force_style(size=size, lang=lang)
        return f"subtitles='{sp}':force_style='{style}'"

    sp = str(sub.resolve()).replace("\\", "/")
    sp = sp.replace("'", r"\'").replace(":", r"\:")
    fdir = Path(get_fonts_dir())
    if fdir.is_dir():
        fd = str(fdir.resolve()).replace("\\", "/").replace("'", r"\'").replace(":", r"\:")
        return f"subtitles='{sp}':fontsdir='{fd}'"
    return f"subtitles='{sp}'"


def drawtext_fallback_filter(
    text: str,
    *,
    size: str = "1080x1920",
    lang: str = "en",
    fontfile: str = "",
) -> str:
    """Last-resort single-line caption (kept small)."""
    w, h = parse_canvas(size)
    fs = max(22, min(34, font_size_for_canvas(w, h) - 8))
    safe = (
        (text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "")
        .replace('"', "")
    )[:72]
    font_opt = f":fontfile='{fontfile}'" if fontfile else ""
    y = max(40, int(h * 0.88))
    return (
        f"drawtext=text='{safe}'{font_opt}:fontcolor=white:fontsize={fs}:"
        f"x=(w-text_w)/2:y={y}:box=1:boxcolor=black@0.35:boxborderw=8"
    )

