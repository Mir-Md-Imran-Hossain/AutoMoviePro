import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import subprocess
from pipeline.compose import ffmpeg_bin
from pipeline.subtitle_burn import get_fonts_dir

ff = ffmpeg_bin()
test_text = "বিজ্ঞানীরা অসম্ভবকে সম্ভব করেছেন মানুষের নরম টিস্যুতে"

out_dir = Path("Output/test_font_renders")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. With UTF-8-SIG (BOM)
ass_bom = out_dir / "test_bom.ass"
ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Nirmala UI,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,60,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{test_text}
"""
ass_bom.write_text(ass_content, encoding="utf-8-sig")

sp = ass_bom.resolve().as_posix().replace(":", r"\:")

# Test 1: With BOM
out_bom_png = out_dir / "test_bom.png"
cmd1 = [
    ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=0.04",
    "-vf", f"subtitles='{sp}'",
    "-vframes", "1", str(out_bom_png)
]
r1 = subprocess.run(cmd1, capture_output=True, text=True, errors="replace")
print("Test 1 (BOM):", r1.returncode, out_bom_png.stat().st_size if out_bom_png.exists() else 0)

# Test 4: With FONTCONFIG_FILE and fontconfig
conf = ROOT / "assets" / "fonts" / "fonts.conf"
env = os.environ.copy()
env["FONTCONFIG_FILE"] = str(conf)
env["FONTCONFIG_PATH"] = str(conf.parent)

out_fc_png = out_dir / "test_fc.png"
cmd4 = [
    ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=0.04",
    "-vf", f"subtitles='{sp}'",
    "-vframes", "1", str(out_fc_png)
]
r4 = subprocess.run(cmd4, capture_output=True, text=True, env=env, errors="replace")
print("Test 4 (FONTCONFIG_FILE):", r4.returncode, out_fc_png.stat().st_size if out_fc_png.exists() else 0)
if r4.returncode != 0:
    print("  error:", r4.stderr[-200:])
