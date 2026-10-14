import os
import math
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = "assets/img"
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H = 800, 450

FONT_ENG_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_ENG_REG = "C:/Windows/Fonts/arial.ttf"

try:
    f_badge = ImageFont.truetype(FONT_ENG_BOLD, 13)
    f_big = ImageFont.truetype(FONT_ENG_BOLD, 22)
    f_title_card = ImageFont.truetype(FONT_ENG_BOLD, 28)
    f_mid = ImageFont.truetype(FONT_ENG_BOLD, 15)
    f_small = ImageFont.truetype(FONT_ENG_REG, 13)
    f_mono = ImageFont.truetype(FONT_ENG_BOLD, 12)
except Exception:
    f_badge = ImageFont.load_default()
    f_big = ImageFont.load_default()
    f_title_card = ImageFont.load_default()
    f_mid = ImageFont.load_default()
    f_small = ImageFont.load_default()
    f_mono = ImageFont.load_default()

def create_base(c_top, c_bot, c_glow):
    img = Image.new("RGBA", (W, H), c_top)
    draw = ImageDraw.Draw(img)
    # Gradient
    for y in range(H):
        ratio = y / float(H)
        r = int(c_top[0] * (1 - ratio) + c_bot[0] * ratio)
        g = int(c_top[1] * (1 - ratio) + c_bot[1] * ratio)
        b = int(c_top[2] * (1 - ratio) + c_bot[2] * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))
    
    # Radial Center Glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    cx, cy = 400, 225
    for rad in range(280, 20, -12):
        alpha = int(55 * (1.0 - rad / 280.0))
        gdraw.ellipse([cx - rad, cy - int(rad * 0.65), cx + rad, cy + int(rad * 0.65)],
                      fill=(c_glow[0], c_glow[1], c_glow[2], alpha))
    img = Image.alpha_composite(img, glow)
    
    # Grid lines
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    griddraw = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        griddraw.line([(x, 0), (x, H)], fill=(255, 255, 255, 10), width=1)
    for y in range(0, H, 40):
        griddraw.line([(0, y), (W, y)], fill=(255, 255, 255, 10), width=1)
    img = Image.alpha_composite(img, grid)

    # Outer border
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([10, 10, W - 10, H - 10], radius=16, outline=(c_glow[0], c_glow[1], c_glow[2], 120), width=2)
    return img

def add_header_badge(draw, text, col):
    w = draw.textlength(text, font=f_badge) + 28
    draw.rounded_rectangle([32, 24, 32 + w, 52], radius=14, fill=(15, 23, 42, 230), outline=col, width=1)
    draw.text((46, 30), text, font=f_badge, fill=col)

def add_footer_glow_strip(draw, title, subtitle, col):
    # Bottom minimal glass pill
    bw = draw.textlength(title, font=f_mid) + draw.textlength(subtitle, font=f_small) + 60
    bx1 = (W - bw) // 2
    by1, by2 = H - 56, H - 24
    draw.rounded_rectangle([bx1, by1, bx1 + bw, by2], radius=16, fill=(10, 16, 30, 230), outline=(col[0], col[1], col[2], 140), width=1)
    draw.ellipse([bx1 + 16, by1 + 10, bx1 + 24, by1 + 18], fill=col)
    draw.text((bx1 + 32, by1 + 7), title, font=f_mid, fill=(255, 255, 255))
    draw.text((bx1 + 38 + draw.textlength(title, font=f_mid), by1 + 8), f"— {subtitle}", font=f_small, fill=(180, 205, 230))


# ==========================================================
# 1. feat-auto-short.png (Vertical Dual Smartphones, 9:16 Shorts)
# ==========================================================
def gen_auto_short():
    img = create_base((20, 10, 36), (36, 12, 54), (236, 72, 153))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "AUTO SHORTS AI STUDIO", (236, 72, 153))

    # Center Smartphone Frame
    px1, py1, px2, py2 = 300, 75, 500, 375
    draw.rounded_rectangle([px1 - 4, py1 - 4, px2 + 4, py2 + 4], radius=26, fill=(25, 12, 40, 240), outline=(236, 72, 153, 200), width=2)
    draw.rounded_rectangle([px1, py1, px2, py2], radius=22, fill=(12, 8, 22, 255))
    # Phone notch & screen
    draw.rounded_rectangle([370, py1 + 8, 430, py1 + 18], radius=5, fill=(35, 15, 45))
    
    # Video preview area
    draw.rounded_rectangle([px1 + 12, py1 + 26, px2 - 12, py2 - 45], radius=12, fill=(30, 14, 52))
    # Play button
    draw.ellipse([380, 175, 420, 215], fill=(236, 72, 153))
    draw.polygon([(395, 185), (412, 195), (395, 205)], fill=(255, 255, 255))
    
    # Audio waves inside phone
    for i in range(16):
        wh = 8 + (i % 6) * 6
        draw.rounded_rectangle([px1 + 25 + i * 9, 310 - wh, px1 + 29 + i * 9, 310], radius=2, fill=(236, 72, 153, 220))
    
    # Left Floating Card
    draw.rounded_rectangle([90, 140, 260, 210], radius=12, fill=(25, 12, 40, 230), outline=(236, 72, 153, 140), width=1)
    draw.text((110, 155), "9:16 VERTICAL", font=f_mid, fill=(255, 120, 190))
    draw.text((110, 180), "Auto Hook & Script", font=f_small, fill=(220, 220, 240))

    # Right Floating Card
    draw.rounded_rectangle([540, 170, 710, 240], radius=12, fill=(25, 12, 40, 230), outline=(139, 92, 246, 140), width=1)
    draw.text((560, 185), "MULTI-PLATFORM", font=f_mid, fill=(190, 140, 255))
    draw.text((560, 210), "YouTube, Reels, TikTok", font=f_small, fill=(220, 220, 240))

    add_footer_glow_strip(draw, "AUTO SHORTS ENGINE", "Automated Viral Short-Form Video Creation", (236, 72, 153))
    img.save(os.path.join(OUTPUT_DIR, "feat-auto-short.png"))

# ==========================================================
# 2. feat-auto-long.png (16:9 Cinema Widescreen Studio)
# ==========================================================
def gen_auto_long():
    img = create_base((10, 22, 42), (8, 32, 58), (6, 182, 212))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "CINEMATIC 16:9 STUDIO", (6, 182, 212))

    # Monitor
    mx1, my1, mx2, my2 = 140, 75, 660, 365
    draw.rounded_rectangle([mx1 - 4, my1 - 4, mx2 + 4, my2 + 4], radius=14, fill=(15, 26, 48, 250), outline=(6, 182, 212, 200), width=2)
    draw.rounded_rectangle([mx1, my1, mx2, my2], radius=10, fill=(6, 16, 32, 255))
    
    # Top studio bar
    draw.rectangle([mx1, my1, mx2, my1 + 32], fill=(12, 30, 55))
    draw.text((mx1 + 20, my1 + 8), "CINEMATIC LONG VIDEO WORKSTATION — 4K 60FPS", font=f_mono, fill=(6, 182, 212))
    draw.text((mx2 - 140, my1 + 8), "TIMELINE: 05:24 / 05:30", font=f_mono, fill=(140, 210, 240))
    
    # 3 Story Scenes
    sw = 150
    for i, title in enumerate(["Scene 1: Viral Hook", "Scene 2: Core Story", "Scene 3: Climax"]):
        sx1 = mx1 + 20 + i * (sw + 16)
        draw.rounded_rectangle([sx1, my1 + 44, sx1 + sw, my1 + 155], radius=8, fill=(18, 38, 70), outline=(56, 189, 248, 90), width=1)
        draw.text((sx1 + 12, my1 + 54), title, font=f_mid, fill=(200, 235, 255))
        # Film thumbnail
        draw.rectangle([sx1 + 12, my1 + 80, sx1 + sw - 12, my1 + 142], fill=(10, 22, 42))
        draw.polygon([(sx1 + 65, my1 + 100), (sx1 + 85, my1 + 111), (sx1 + 65, my1 + 122)], fill=(6, 182, 212))
    
    # Timeline
    draw.rectangle([mx1 + 20, my1 + 170, mx2 - 20, my1 + 270], fill=(10, 24, 46))
    draw.text((mx1 + 30, my1 + 178), "TRACK 1: 4K UHD Cinematic Visuals", font=f_mono, fill=(56, 189, 248))
    draw.rectangle([mx1 + 250, my1 + 178, mx2 - 30, my1 + 194], fill=(2, 132, 199, 180))
    
    draw.text((mx1 + 30, my1 + 206), "TRACK 2: Human Voiceover Engine", font=f_mono, fill=(52, 211, 153))
    draw.rectangle([mx1 + 250, my1 + 206, mx2 - 80, my1 + 222], fill=(5, 150, 105, 180))
    
    draw.text((mx1 + 30, my1 + 234), "TRACK 3: HarfBuzz Dynamic Subtitles", font=f_mono, fill=(251, 191, 36))
    draw.rectangle([mx1 + 250, my1 + 234, mx2 - 45, my1 + 250], fill=(217, 119, 6, 180))

    add_footer_glow_strip(draw, "AUTO LONG VIDEO STUDIO", "5+ Minute Storytelling with Dynamic Pacing & 4K", (6, 182, 212))
    img.save(os.path.join(OUTPUT_DIR, "feat-auto-long.png"))

# ==========================================================
# 3. feat-six-langs.png (6 Global Languages from 1 Master)
# ==========================================================
def gen_six_langs():
    img = create_base((8, 26, 32), (12, 42, 48), (20, 184, 166))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "6 GLOBAL MARKETS SYNC", (20, 184, 166))

    cx, cy = 400, 205
    # Center Master Hub
    draw.ellipse([cx - 55, cy - 55, cx + 55, cy + 55], fill=(15, 38, 48, 250), outline=(20, 184, 166, 220), width=3)
    draw.text((cx - 32, cy - 16), "1 MASTER", font=f_big, fill=(255, 255, 255))
    draw.text((cx - 24, cy + 12), "CLIP AI", font=f_mono, fill=(20, 184, 166))
    
    langs = [
        ("EN", "English Global", -170, -85),
        ("BN", "Bangla Native", 0, -115),
        ("HI", "Hindi Regional", 170, -85),
        ("UR", "Urdu Regional", 185, 45),
        ("TA", "Tamil Market", 70, 110),
        ("ML", "Malayalam Market", -145, 90)
    ]
    for code, name, ox, oy in langs:
        lx, ly = cx + ox, cy + oy
        draw.line([(cx, cy), (lx, ly)], fill=(20, 184, 166, 140), width=2)
        draw.rounded_rectangle([lx - 75, ly - 22, lx + 75, ly + 22], radius=12, fill=(14, 32, 44, 240), outline=(45, 212, 191, 180), width=1)
        draw.text((lx - 62, ly - 9), f"[{code}] {name}", font=f_mid, fill=(230, 255, 250))

    add_footer_glow_strip(draw, "MULTI-LANGUAGE SYNC", "One Video Master Localized to 6 High-RPM Markets", (20, 184, 166))
    img.save(os.path.join(OUTPUT_DIR, "feat-six-langs.png"))

# ==========================================================
# 4. feat-yt6.png (Up to 6 YouTube Channels)
# ==========================================================
def gen_yt6():
    img = create_base((32, 10, 14), (48, 12, 18), (239, 68, 68))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "YOUTUBE MULTI-STREAM", (239, 68, 68))

    cx_list = [150, 315, 480, 645, 230, 560]
    cy_list = [130, 130, 130, 130, 250, 250]
    for i in range(6):
        x, y = cx_list[i], cy_list[i]
        w, h = 145, 95
        draw.rounded_rectangle([x - w//2, y - h//2, x + w//2, y + h//2], radius=12, fill=(28, 14, 18, 240), outline=(239, 68, 68, 150), width=1)
        # Red Play Button
        draw.rounded_rectangle([x - w//2 + 12, y - h//2 + 12, x - w//2 + 40, y - h//2 + 32], radius=5, fill=(239, 68, 68))
        draw.polygon([(x - w//2 + 22, y - h//2 + 17), (x - w//2 + 32, y - h//2 + 22), (x - w//2 + 22, y - h//2 + 27)], fill=(255, 255, 255))
        draw.text((x - w//2 + 48, y - h//2 + 14), f"Channel #{i+1}", font=f_mid, fill=(255, 220, 220))
        draw.text((x - w//2 + 14, y - h//2 + 42), "MONETIZED ($)", font=f_mono, fill=(74, 222, 128))
        draw.text((x - w//2 + 14, y - h//2 + 64), f"Subs: +{(i+2)*35}K", font=f_small, fill=(240, 240, 250))

    add_footer_glow_strip(draw, "6 YOUTUBE CHANNELS", "Independent Automated Video Scheduling & Monetization", (239, 68, 68))
    img.save(os.path.join(OUTPUT_DIR, "feat-yt6.png"))

# ==========================================================
# 5. feat-fb6.png (Up to 6 Facebook Pages & Reels)
# ==========================================================
def gen_fb6():
    img = create_base((10, 20, 48), (16, 32, 68), (37, 99, 235))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "META FB BUSINESS SUITE", (59, 130, 246))

    cx_list = [150, 315, 480, 645, 230, 560]
    cy_list = [130, 130, 130, 130, 250, 250]
    for i in range(6):
        x, y = cx_list[i], cy_list[i]
        w, h = 145, 95
        draw.rounded_rectangle([x - w//2, y - h//2, x + w//2, y + h//2], radius=12, fill=(16, 26, 52, 240), outline=(59, 130, 246, 150), width=1)
        # Blue F Icon
        draw.ellipse([x - w//2 + 12, y - h//2 + 12, x - w//2 + 34, y - h//2 + 34], fill=(37, 99, 235))
        draw.text((x - w//2 + 18, y - h//2 + 13), "f", font=f_mid, fill=(255, 255, 255))
        draw.text((x - w//2 + 42, y - h//2 + 14), f"FB Page #{i+1}", font=f_mid, fill=(220, 235, 255))
        draw.text((x - w//2 + 14, y - h//2 + 42), "REELS AUTOPILOT", font=f_mono, fill=(56, 189, 248))
        draw.text((x - w//2 + 14, y - h//2 + 64), f"Reach: {(i+1)*55}K", font=f_small, fill=(74, 222, 128))

    add_footer_glow_strip(draw, "6 FACEBOOK DESTINATIONS", "Pages, Reels & Ad Campaigns Handled Simultaneously", (59, 130, 246))
    img.save(os.path.join(OUTPUT_DIR, "feat-fb6.png"))

# ==========================================================
# 6. feat-tt6.png (Up to 6 TikTok Channels)
# ==========================================================
def gen_tt6():
    img = create_base((14, 14, 22), (22, 22, 32), (0, 242, 254))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "TIKTOK VIRAL NETWORK", (0, 242, 254))

    cx_list = [150, 315, 480, 645, 230, 560]
    cy_list = [130, 130, 130, 130, 250, 250]
    for i in range(6):
        x, y = cx_list[i], cy_list[i]
        w, h = 145, 95
        draw.rounded_rectangle([x - w//2, y - h//2, x + w//2, y + h//2], radius=12, fill=(20, 20, 28, 240), outline=(255, 0, 127, 140), width=1)
        # Neon Icon
        draw.rounded_rectangle([x - w//2 + 10, y - h//2 + 10, x - w//2 + 32, y - h//2 + 32], radius=6, fill=(0, 242, 254))
        draw.polygon([(x - w//2 + 18, y - h//2 + 16), (x - w//2 + 25, y - h//2 + 21), (x - w//2 + 18, y - h//2 + 26)], fill=(0, 0, 0))
        draw.text((x - w//2 + 40, y - h//2 + 14), f"TikTok #{i+1}", font=f_mid, fill=(255, 255, 255))
        draw.text((x - w//2 + 14, y - h//2 + 42), "VIRAL REWARD", font=f_mono, fill=(255, 0, 127))
        draw.text((x - w//2 + 14, y - h//2 + 64), f"Views: {(i+1)*320}K", font=f_small, fill=(0, 242, 254))

    add_footer_glow_strip(draw, "6 TIKTOK DESTINATIONS", "Capture High-Growth Short-Form Audiences Across 6 Feeds", (0, 242, 254))
    img.save(os.path.join(OUTPUT_DIR, "feat-tt6.png"))

# ==========================================================
# 7. feat-connect.png (Connect Once, Stay Logged In)
# ==========================================================
def gen_connect():
    img = create_base((8, 28, 20), (14, 45, 32), (16, 185, 129))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "PERSISTENT SESSION VAULT", (16, 185, 129))

    cx, cy = 400, 200
    # Vault Card
    draw.rounded_rectangle([cx - 180, cy - 110, cx + 180, cy + 110], radius=20, fill=(15, 36, 26, 245), outline=(16, 185, 129, 200), width=2)
    # Padlock
    draw.ellipse([cx - 30, cy - 75, cx + 30, cy - 20], outline=(16, 185, 129), width=8)
    draw.rounded_rectangle([cx - 45, cy - 40, cx + 45, cy + 35], radius=12, fill=(16, 185, 129))
    draw.ellipse([cx - 10, cy - 12, cx + 10, cy + 8], fill=(10, 30, 20))
    draw.line([(cx, cy + 8), (cx, cy + 22)], fill=(10, 30, 20), width=4)
    
    draw.text((cx - 130, cy + 50), "1-CLICK PERSISTENT SESSION", font=f_mid, fill=(230, 255, 240))
    draw.text((cx - 145, cy + 74), "Encrypted Cookies • Zero Daily Password Prompts", font=f_small, fill=(140, 225, 180))

    add_footer_glow_strip(draw, "ONE-TIME LOGIN SECURITY", "Connect Once, Save Session & Publish Daily Without Obstacles", (16, 185, 129))
    img.save(os.path.join(OUTPUT_DIR, "feat-connect.png"))

# ==========================================================
# 8. feat-niche-seo.png (Niche + High-CTR SEO Titles)
# ==========================================================
def gen_niche_seo():
    img = create_base((32, 22, 10), (48, 32, 14), (245, 158, 11))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "HIGH-CTR SEO ARCHITECT", (245, 158, 11))

    # Target Left
    cx, cy = 250, 200
    for r, col in [(85, (245, 158, 11, 40)), (65, (245, 158, 11, 80)), (45, (245, 158, 11, 140)), (25, (245, 158, 11, 230))]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(245, 158, 11), width=1)
    draw.text((cx - 18, cy - 10), "SEO", font=f_mid, fill=(255, 255, 255))
    
    # Card Right
    draw.rounded_rectangle([380, 100, 680, 300], radius=16, fill=(26, 20, 12, 245), outline=(245, 158, 11, 160), width=1)
    draw.text((405, 120), "VIRAL CLICKABILITY SCORE", font=f_mid, fill=(245, 158, 11))
    draw.text((405, 150), "99/100 (Optimal CTR)", font=f_big, fill=(74, 222, 128))
    draw.text((405, 190), "• Emotional Curiosity Gap Hooks", font=f_small, fill=(255, 235, 190))
    draw.text((405, 218), "• Trending Multi-Lingual Keywords", font=f_small, fill=(255, 235, 190))
    draw.text((405, 246), "• Search-Ranked Hashtag Generator", font=f_small, fill=(255, 235, 190))

    add_footer_glow_strip(draw, "NICHE & HIGH-CTR SEO", "Maximized Organic Reach via Targeted Algorithmic Copy", (245, 158, 11))
    img.save(os.path.join(OUTPUT_DIR, "feat-niche-seo.png"))

# ==========================================================
# 9. feat-agnes.png (Agnes Video Generation / Veo-3)
# ==========================================================
def gen_agnes():
    img = create_base((26, 10, 42), (40, 14, 62), (168, 85, 247))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "VEO-3 & NANO BANANA AI", (168, 85, 247))

    cx, cy = 400, 200
    # Optical Aperture
    draw.ellipse([cx - 85, cy - 85, cx + 85, cy + 85], fill=(22, 12, 38, 250), outline=(168, 85, 247), width=3)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = cx + int(48 * math.cos(rad))
        y1 = cy + int(48 * math.sin(rad))
        x2 = cx + int(82 * math.cos(rad + 0.6))
        y2 = cy + int(82 * math.sin(rad + 0.6))
        draw.line([(x1, y1), (x2, y2)], fill=(168, 85, 247, 180), width=2)
    
    draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(168, 85, 247))
    draw.text((cx - 24, cy - 12), "AI", font=f_big, fill=(255, 255, 255))
    
    draw.rounded_rectangle([90, 165, 275, 235], radius=12, fill=(26, 12, 42, 230), outline=(192, 132, 252, 140), width=1)
    draw.text((110, 182), "ULTRA-HD MOTION", font=f_mid, fill=(216, 180, 254))
    draw.text((110, 206), "Studio-Grade Physics", font=f_small, fill=(230, 210, 250))

    draw.rounded_rectangle([525, 165, 710, 235], radius=12, fill=(26, 12, 42, 230), outline=(192, 132, 252, 140), width=1)
    draw.text((545, 182), "PRO VIDEO ENGINE", font=f_mid, fill=(216, 180, 254))
    draw.text((545, 206), "Zero Robotic Artifacts", font=f_small, fill=(230, 210, 250))

    add_footer_glow_strip(draw, "AGNES CINEMATIC AI", "Lifelike Motion Synthesis and Ultra-HD Visual Generation", (168, 85, 247))
    img.save(os.path.join(OUTPUT_DIR, "feat-agnes.png"))

# ==========================================================
# 10. feat-image-fallback.png (Image-to-Video Fallback)
# ==========================================================
def gen_image_fallback():
    img = create_base((32, 16, 8), (50, 26, 14), (249, 115, 22))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "100% ZERO-FAIL BACKUP", (249, 115, 22))

    # Flowchart
    draw.rounded_rectangle([110, 140, 280, 240], radius=14, fill=(35, 18, 12, 240), outline=(249, 115, 22, 160), width=1)
    draw.text((130, 165), "PRIMARY ROUTE", font=f_mid, fill=(255, 180, 140))
    draw.text((130, 195), "Veo-3 AI Video Model", font=f_small, fill=(240, 240, 250))

    # Sensor
    draw.line([(280, 190), (360, 190)], fill=(249, 115, 22), width=3)
    draw.polygon([(360, 184), (374, 190), (360, 196)], fill=(249, 115, 22))

    draw.ellipse([385, 160, 445, 220], fill=(50, 25, 15), outline=(251, 146, 60), width=2)
    draw.text((400, 178), "AUTO", font=f_mono, fill=(255, 255, 255))
    draw.text((400, 194), "SWITCH", font=f_mono, fill=(251, 146, 60))

    # Route B
    draw.line([(445, 190), (525, 190)], fill=(34, 197, 94), width=3)
    draw.polygon([(525, 184), (539, 190), (525, 196)], fill=(34, 197, 94))

    draw.rounded_rectangle([540, 140, 710, 240], radius=14, fill=(15, 36, 22, 240), outline=(34, 197, 94, 180), width=1)
    draw.text((560, 165), "FAILOVER SYSTEM", font=f_mid, fill=(160, 255, 180))
    draw.text((560, 195), "Ken-Burns Neural Motion", font=f_small, fill=(74, 222, 128))

    add_footer_glow_strip(draw, "SMART FAILOVER ENGINE", "Never Frozen Clips — Automatic Fallback Ensures Delivery", (249, 115, 22))
    img.save(os.path.join(OUTPUT_DIR, "feat-image-fallback.png"))

# ==========================================================
# 11. feat-human-browser.png (Human-Like Browser Actions)
# ==========================================================
def gen_human_browser():
    img = create_base((8, 26, 26), (14, 42, 42), (13, 148, 136))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "STEALTH HUMAN EMULATOR", (13, 148, 136))

    cx, cy = 400, 195
    # Shield
    draw.polygon([(cx, cy - 85), (cx + 85, cy - 45), (cx + 65, cy + 65), (cx, cy + 95), (cx - 65, cy + 65), (cx - 85, cy - 45)],
                 fill=(14, 38, 38, 240), outline=(13, 148, 136), width=2)
    # Cursor
    draw.polygon([(cx - 16, cy - 26), (cx + 16, cy), (cx + 2, cy + 6), (cx + 8, cy + 24), (cx - 2, cy + 28), (cx - 8, cy + 10), (cx - 24, cy + 14)],
                 fill=(45, 212, 191), outline=(255, 255, 255), width=1)
    
    draw.rounded_rectangle([90, 150, 275, 230], radius=12, fill=(14, 34, 34, 230), outline=(45, 212, 191, 140), width=1)
    draw.text((105, 168), "ORGANIC BEZIER PATH", font=f_mid, fill=(45, 212, 191))
    draw.text((105, 196), "Micro-delays & Smooth Jitter", font=f_small, fill=(200, 240, 235))

    draw.rounded_rectangle([525, 150, 710, 230], radius=12, fill=(14, 34, 34, 230), outline=(45, 212, 191, 140), width=1)
    draw.text((545, 168), "TYPING SIMULATION", font=f_mid, fill=(45, 212, 191))
    draw.text((545, 196), "Realistic Key Stroke Intervals", font=f_small, fill=(200, 240, 235))

    add_footer_glow_strip(draw, "STEALTH BROWSER ACTIONS", "Human-Like Mouse Paths & Rhythms Prevent Account Flags", (13, 148, 136))
    img.save(os.path.join(OUTPUT_DIR, "feat-human-browser.png"))

# ==========================================================
# 12. feat-agent.png (In-App Helper Agent)
# ==========================================================
def gen_agent():
    img = create_base((10, 24, 46), (18, 36, 68), (56, 189, 248))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "DESKTOP ASSISTANT SENTINEL", (56, 189, 248))

    cx, cy = 400, 195
    # Robot Head
    draw.rounded_rectangle([cx - 55, cy - 55, cx + 55, cy + 55], radius=20, fill=(20, 38, 70, 250), outline=(56, 189, 248), width=2)
    draw.ellipse([cx - 32, cy - 16, cx - 12, cy + 6], fill=(56, 189, 248))
    draw.ellipse([cx + 12, cy - 16, cx + 32, cy + 6], fill=(56, 189, 248))
    draw.rounded_rectangle([cx - 24, cy + 22, cx + 24, cy + 28], radius=3, fill=(56, 189, 248))
    # Headset
    draw.arc([cx - 68, cy - 50, cx + 68, cy + 50], start=180, end=360, fill=(255, 255, 255), width=4)
    draw.ellipse([cx - 72, cy - 6, cx - 54, cy + 26], fill=(56, 189, 248))
    draw.ellipse([cx + 54, cy - 6, cx + 72, cy + 26], fill=(56, 189, 248))

    draw.rounded_rectangle([95, 150, 280, 230], radius=12, fill=(16, 30, 56, 230), outline=(56, 189, 248, 140), width=1)
    draw.text((115, 168), "AUTOMATED SETUP", font=f_mid, fill=(200, 235, 255))
    draw.text((115, 196), "Configures APIs & Browser", font=f_small, fill=(180, 210, 240))

    draw.rounded_rectangle([520, 150, 705, 230], radius=12, fill=(16, 30, 56, 230), outline=(52, 211, 153, 140), width=1)
    draw.text((540, 168), "CAPTCHA ALERT", font=f_mid, fill=(160, 255, 200))
    draw.text((540, 196), "24/7 Mobile Companion UI", font=f_small, fill=(180, 210, 240))

    add_footer_glow_strip(draw, "24/7 DESKTOP HELPER", "Guided Setup, Key Management and Mobile Interconnect", (56, 189, 248))
    img.save(os.path.join(OUTPUT_DIR, "feat-agent.png"))

# ==========================================================
# 13. feat-schedule.png (Upload Scheduler)
# ==========================================================
def gen_schedule():
    img = create_base((18, 14, 42), (30, 18, 62), (99, 102, 241))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "AUTOPILOT SCHEDULER", (99, 102, 241))

    # Clock
    cx, cy = 250, 200
    draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], fill=(22, 18, 50, 250), outline=(99, 102, 241), width=2)
    draw.line([(cx, cy), (cx, cy - 50)], fill=(255, 255, 255), width=3)
    draw.line([(cx, cy), (cx + 40, cy + 15)], fill=(129, 140, 248), width=3)
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(99, 102, 241))
    
    # Slots Right
    draw.rounded_rectangle([380, 100, 680, 300], radius=16, fill=(24, 18, 52, 245), outline=(99, 102, 241, 160), width=1)
    draw.text((405, 120), "DAILY PUBLISHING WINDOWS", font=f_mid, fill=(165, 180, 252))
    
    slots = [("10:30 AM", "Morning Short • YouTube & TikTok", (74, 222, 128)),
             ("03:00 PM", "Afternoon Post • FB Business Pages", (96, 165, 250)),
             ("08:30 PM", "Prime Time • Cinematic Long Video", (244, 114, 182))]
    for i, (time_str, desc, col) in enumerate(slots):
        sy = 158 + i * 42
        draw.rounded_rectangle([405, sy, 480, sy + 28], radius=6, fill=col)
        draw.text((414, sy + 6), time_str, font=f_mono, fill=(15, 23, 42))
        draw.text((495, sy + 6), desc, font=f_small, fill=(230, 230, 250))

    add_footer_glow_strip(draw, "24/7 AUTO SCHEDULER", "Hands-Free Publishing on Your Exact Daily Timetable", (99, 102, 241))
    img.save(os.path.join(OUTPUT_DIR, "feat-schedule.png"))

# ==========================================================
# 14. feat-insights.png (Post Insights & Replies)
# ==========================================================
def gen_insights():
    img = create_base((8, 26, 24), (14, 40, 34), (52, 211, 153))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "REAL-TIME ANALYTICS HUB", (52, 211, 153))

    mx1, my1, mx2, my2 = 150, 95, 650, 295
    draw.rounded_rectangle([mx1, my1, mx2, my2], radius=16, fill=(14, 32, 26, 245), outline=(52, 211, 153, 150), width=1)
    
    for i in range(4):
        gy = my1 + 45 + i * 40
        draw.line([(mx1 + 24, gy), (mx2 - 24, gy)], fill=(52, 211, 153, 35), width=1)
    
    pts = [(mx1 + 50, my2 - 35), (mx1 + 140, my2 - 50), (mx1 + 230, my2 - 95),
           (mx1 + 320, my2 - 80), (mx1 + 410, my2 - 135), (mx2 - 50, my2 - 165)]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i+1]], fill=(52, 211, 153), width=4)
        draw.ellipse([pts[i][0] - 6, pts[i][1] - 6, pts[i][0] + 6, pts[i][1] + 6], fill=(255, 255, 255))
    draw.ellipse([pts[-1][0] - 7, pts[-1][1] - 7, pts[-1][0] + 7, pts[-1][1] + 7], fill=(52, 211, 153))
    
    draw.text((mx1 + 24, my1 + 14), "ENGAGEMENT SPIKE & COMMENT RESPONSES", font=f_mid, fill=(52, 211, 153))
    draw.text((mx2 - 150, my1 + 14), "+380% GROWTH", font=f_mid, fill=(255, 255, 255))

    add_footer_glow_strip(draw, "POST INSIGHTS & REPLIES", "Live Metrics, Retention Curves and Smart Auto-Comment Tools", (52, 211, 153))
    img.save(os.path.join(OUTPUT_DIR, "feat-insights.png"))

# ==========================================================
# 15. feat-lifetime.png (One-time price + language add-ons)
# ==========================================================
def gen_lifetime():
    img = create_base((32, 26, 8), (50, 38, 12), (234, 179, 8))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "LIFETIME VIP OWNERSHIP", (234, 179, 8))

    cx, cy = 400, 195
    draw.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(36, 28, 12, 250), outline=(234, 179, 8), width=3)
    draw.ellipse([cx - 75, cy - 75, cx + 75, cy + 75], outline=(250, 204, 21), width=1)
    
    draw.text((cx - 55, cy - 38), "100%", font=f_title_card, fill=(250, 204, 21))
    draw.text((cx - 60, cy - 4), "LIFETIME", font=f_mid, fill=(255, 255, 255))
    draw.text((cx - 56, cy + 22), "NO SUBSCRIPTIONS", font=f_mono, fill=(234, 179, 8))

    draw.rounded_rectangle([90, 160, 275, 230], radius=12, fill=(36, 28, 12, 230), outline=(234, 179, 8, 140), width=1)
    draw.text((110, 178), "ONE-TIME PAYMENT", font=f_mid, fill=(250, 204, 21))
    draw.text((110, 202), "English + 1 Native Lang", font=f_small, fill=(230, 220, 190))

    draw.rounded_rectangle([525, 160, 710, 230], radius=12, fill=(36, 28, 12, 230), outline=(234, 179, 8, 140), width=1)
    draw.text((545, 178), "FREE UPDATES", font=f_mid, fill=(250, 204, 21))
    draw.text((545, 202), "Lifetime Software Bugfixes", font=f_small, fill=(230, 220, 190))

    add_footer_glow_strip(draw, "LIFETIME LICENSE", "Zero Monthly Fees — Own Forever with Free Performance Upgrades", (234, 179, 8))
    img.save(os.path.join(OUTPUT_DIR, "feat-lifetime.png"))

# ==========================================================
# 16. feat-dream.png (Dream Automatic Content Creator)
# ==========================================================
def gen_dream():
    img = create_base((10, 22, 48), (16, 34, 70), (37, 99, 235))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "AUTONOMOUS CONTENT FACTORY", (37, 99, 235))

    mx1, my1, mx2, my2 = 140, 85, 660, 305
    draw.rounded_rectangle([mx1, my1, mx2, my2], radius=16, fill=(14, 26, 52, 245), outline=(37, 99, 235, 160), width=2)
    
    # Gears
    cx1, cy1 = 250, 195
    draw.ellipse([cx1 - 45, cy1 - 45, cx1 + 45, cy1 + 45], outline=(56, 189, 248), width=3)
    draw.text((cx1 - 20, cy1 - 14), "GEAR", font=f_mono, fill=(56, 189, 248))
    
    cx2, cy2 = 340, 170
    draw.ellipse([cx2 - 32, cy2 - 32, cx2 + 32, cy2 + 32], outline=(96, 165, 250), width=2)
    draw.text((cx2 - 16, cy2 - 10), "AI", font=f_mono, fill=(96, 165, 250))

    draw.rounded_rectangle([420, 115, 630, 180], radius=10, fill=(16, 32, 64), outline=(74, 222, 128, 140), width=1)
    draw.text((440, 132), "YOUTUBE REVENUE STREAM", font=f_mid, fill=(74, 222, 128))
    draw.text((440, 154), "Global Passive RPM Accumulation", font=f_small, fill=(200, 230, 255))

    draw.rounded_rectangle([420, 200, 630, 265], radius=10, fill=(16, 32, 64), outline=(56, 189, 248, 140), width=1)
    draw.text((440, 216), "CROSS-PLATFORM GROWTH", font=f_mid, fill=(56, 189, 248))
    draw.text((440, 238), "PC Runs Autonomously 24/7", font=f_small, fill=(200, 230, 255))

    add_footer_glow_strip(draw, "DREAM CONTENT CREATOR", "Turn Your PC into a Self-Driving Multi-Channel Media Factory", (37, 99, 235))
    img.save(os.path.join(OUTPUT_DIR, "feat-dream.png"))

# ==========================================================
# 17. feat-omnisocial.png (OmniSocial AI Hub & Healer)
# ==========================================================
def gen_omnisocial():
    img = create_base((34, 10, 20), (50, 14, 28), (225, 29, 72))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "OMNISOCIAL AUTO HEALER", (225, 29, 72))

    cx, cy = 400, 195
    for r in [95, 70, 45]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(225, 29, 72, 130), width=1)
    draw.line([(cx - 95, cy), (cx + 95, cy)], fill=(225, 29, 72, 90), width=1)
    draw.line([(cx, cy - 95), (cx, cy + 95)], fill=(225, 29, 72, 90), width=1)
    
    draw.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(225, 29, 72))
    draw.text((cx - 16, cy - 10), "RADAR", font=f_mono, fill=(255, 255, 255))
    
    draw.rounded_rectangle([90, 160, 275, 230], radius=12, fill=(36, 14, 22, 230), outline=(244, 63, 94, 160), width=1)
    draw.text((105, 178), "AUTO-POST REPAIR", font=f_mid, fill=(251, 113, 133))
    draw.text((105, 202), "Detects & Heals Broken Posts", font=f_small, fill=(240, 200, 210))

    draw.rounded_rectangle([525, 160, 710, 230], radius=12, fill=(36, 14, 22, 230), outline=(244, 63, 94, 160), width=1)
    draw.text((545, 178), "30s CHROME WATCHDOG", font=f_mid, fill=(251, 113, 133))
    draw.text((545, 202), "Graceful Timeout Recovery", font=f_small, fill=(240, 200, 210))

    add_footer_glow_strip(draw, "SELF-HEALING AUTOPILOT", "Continuous Post Inspection, Healer Sentinel & Process Guard", (225, 29, 72))
    img.save(os.path.join(OUTPUT_DIR, "feat-omnisocial.png"))

# ==========================================================
# 18. feat-sharer-stories.png (Targeted Community Sharer & Stories)
# ==========================================================
def gen_sharer_stories():
    img = create_base((16, 20, 48), (22, 26, 68), (59, 130, 246))
    draw = ImageDraw.Draw(img)
    add_header_badge(draw, "COMMUNITY SHARER & STORIES", (59, 130, 246))

    # Left Groups
    draw.rounded_rectangle([110, 105, 370, 290], radius=16, fill=(16, 26, 56, 245), outline=(59, 130, 246, 150), width=1)
    draw.text((130, 128), "TARGETED GROUP SHARER", font=f_mid, fill=(96, 165, 250))
    draw.text((130, 162), "• 1-2 Safe Shares / Day (Anti-Ban)", font=f_small, fill=(210, 230, 255))
    draw.text((130, 192), "• Keyword Niche Matching", font=f_small, fill=(210, 230, 255))
    draw.text((130, 222), "• 100% Organic Reach Boost", font=f_small, fill=(74, 222, 128))
    draw.text((130, 252), "• Avoids Flagged Suspicious Groups", font=f_small, fill=(210, 230, 255))

    # Right Story Card
    sx1, sy1, sx2, sy2 = 430, 95, 690, 295
    draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=16, fill=(24, 18, 52, 245), outline=(168, 85, 247, 160), width=1)
    draw.text((455, 120), "9:16 DAILY STORY PUBLISHER", font=f_mid, fill=(216, 180, 254))
    draw.rounded_rectangle([455, 150, 665, 235], radius=10, fill=(36, 22, 64))
    draw.text((475, 180), "STORY GENERATED & UPLOADED", font=f_mid, fill=(255, 255, 255))
    draw.text((455, 255), "Auto-Posted to Facebook & Instagram Stories", font=f_small, fill=(195, 175, 235))

    add_footer_glow_strip(draw, "ORGANIC SHARER & STORIES", "Targeted Community Sharing + Automatic Daily 9:16 Stories", (59, 130, 246))
    img.save(os.path.join(OUTPUT_DIR, "feat-sharer-stories.png"))


if __name__ == "__main__":
    print("Generating 18 pristine feature graphics with zero missing glyphs...")
    gen_auto_short()
    gen_auto_long()
    gen_six_langs()
    gen_yt6()
    gen_fb6()
    gen_tt6()
    gen_connect()
    gen_niche_seo()
    gen_agnes()
    gen_image_fallback()
    gen_human_browser()
    gen_agent()
    gen_schedule()
    gen_insights()
    gen_lifetime()
    gen_dream()
    gen_omnisocial()
    gen_sharer_stories()
    print("All 18 feature graphics generated successfully!")
