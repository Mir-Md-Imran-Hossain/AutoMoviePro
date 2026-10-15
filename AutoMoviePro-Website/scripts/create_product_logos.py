"""
=============================================================================
AutoMovie Pro - Distinct Product Logos Generator
=============================================================================
Generates 3 distinct product logos matching the 3D cinematic brand identity:
1. Video Content Studio (Electric Cyan & Neon Blue)
2. FB Business Manager & Ad Engine (Royal Cyber Violet & Magenta Glow)
3. FB Profile & Page Social AutoPilot (Vivid Emerald Green & Cyber Teal)

Outputs high-resolution 1024x1024, 512x512, and 256x256 transparent PNGs
for the Website, Software apps, and Social Automation Hub.
=============================================================================
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

ROOT_DIR = r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update"
WEBSITE_IMG_DIR = os.path.join(ROOT_DIR, "AutoMoviePro-Website", "assets", "img")
SOFTWARE_IMG_DIR = os.path.join(ROOT_DIR, "AutoMoviePro-Software", "ui", "img")
SOCIAL_MANAGER_IMG_DIR = r"E:\All Project\Socialmedia_Maneger\static\img"
AUTOMATIONS_DIR = r"E:\AI Assistant\Automations"

for d in [WEBSITE_IMG_DIR, SOFTWARE_IMG_DIR, SOCIAL_MANAGER_IMG_DIR, AUTOMATIONS_DIR]:
    os.makedirs(d, exist_ok=True)

MASTER_LOGO_PATH = os.path.join(WEBSITE_IMG_DIR, "logo.png")

def get_font(size: int, bold: bool = True):
    font_candidates = [
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        os.path.join(ROOT_DIR, "AutoMoviePro-Software", "assets", "fonts", "PotroSansBangla-Bold.ttf")
    ]
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()

def draw_pill_badge(draw: ImageDraw.ImageDraw, box, fill_color, border_color, glow_color, border_width=4):
    x0, y0, x1, y1 = box
    r = (y1 - y0) / 2
    # Draw glow
    for g in range(6, 0, -2):
        draw.rounded_rectangle([x0 - g, y0 - g, x1 + g, y1 + g], radius=r + g, outline=glow_color, width=2)
    # Draw background
    draw.rounded_rectangle(box, radius=r, fill=fill_color, outline=border_color, width=border_width)

def recolor_master_badge(master_img: Image.Image, target_hue: str) -> Image.Image:
    """
    Recolors the outer cyan/blue neon ring and interior glow of the badge to target hue:
    - 'cyan': Keep electric cyan / blue (video studio)
    - 'magenta': Shift cyan/blue to neon purple / magenta / violet (fb business)
    - 'emerald': Shift cyan/blue to vivid emerald / neon teal (social autopilot)
    """
    img = master_img.convert("RGBA")
    arr = np.array(img).astype(np.float32)
    
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    a = arr[:, :, 3]

    if target_hue == "cyan":
        # Boost cyan saturation & brightness slightly
        cyan_mask = (b > 80) & (g > 50) & (b > r + 15)
        arr[cyan_mask, 0] = np.clip(arr[cyan_mask, 0] * 0.9, 0, 255)
        arr[cyan_mask, 1] = np.clip(arr[cyan_mask, 1] * 1.15, 0, 255)
        arr[cyan_mask, 2] = np.clip(arr[cyan_mask, 2] * 1.15, 0, 255)

    elif target_hue == "magenta":
        # Convert blue/cyan pixels to rich royal magenta / purple
        cyan_mask = (b > 60) | (g > 80)
        # Shift: R = B, G = G * 0.35, B = B * 1.1
        new_r = np.clip(b * 1.15 + r * 0.5, 0, 255)
        new_g = np.clip(g * 0.35 + r * 0.2, 0, 255)
        new_b = np.clip(b * 1.1 + g * 0.4, 0, 255)
        
        mix = np.clip((b - r * 0.5) / 100.0, 0.0, 1.0)[:, :, np.newaxis]
        orig_rgb = arr[:, :, :3]
        target_rgb = np.dstack([new_r, new_g, new_b])
        arr[:, :, :3] = orig_rgb * (1.0 - mix) + target_rgb * mix

    elif target_hue == "emerald":
        # Convert blue/cyan pixels to vivid emerald green / cyber teal
        cyan_mask = (b > 60) | (g > 60)
        new_r = np.clip(r * 0.3 + g * 0.2, 0, 255)
        new_g = np.clip(g * 1.25 + b * 0.4, 0, 255)
        new_b = np.clip(b * 0.45 + g * 0.3, 0, 255)
        
        mix = np.clip((b + g * 0.5 - r) / 120.0, 0.0, 1.0)[:, :, np.newaxis]
        orig_rgb = arr[:, :, :3]
        target_rgb = np.dstack([new_r, new_g, new_b])
        arr[:, :, :3] = orig_rgb * (1.0 - mix) + target_rgb * mix

    arr[:, :, 3] = a
    return Image.fromarray(arr.astype(np.uint8), "RGBA")

def build_video_studio_logo(master_img: Image.Image) -> Image.Image:
    """
    Product 1: AutoMovie Pro - Video Content Studio (৳3,999)
    Electric Cyan & Deep Sapphire Blue.
    Centerpiece: Cinematic Lens, Film Reel, AI 4K sparkle.
    """
    img = recolor_master_badge(master_img, "cyan").resize((1024, 1024), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    cx, cy = w // 2, h // 2

    # Draw bottom pill badge ribbon: "VIDEO STUDIO"
    badge_w, badge_h = 580, 84
    bx0, by0 = cx - badge_w // 2, int(h * 0.77)
    bx1, by1 = bx0 + badge_w, by0 + badge_h

    # Glow layer
    draw_pill_badge(draw, [bx0, by0, bx1, by1],
                    fill_color=(5, 15, 35, 245),
                    border_color=(0, 240, 255, 255),
                    glow_color=(0, 200, 255, 60),
                    border_width=4)

    # Text "VIDEO STUDIO"
    font = get_font(44)
    text = "VIDEO CONTENT STUDIO"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2
    ty = by0 + (badge_h - th) // 2 - 4

    # Text shadow & cyan glow
    draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 30, 60, 220))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Top mini label: "4K AI AUTOMATION"
    sub_font = get_font(20)
    sub_text = "✦ 4K AI CINEMATIC ENGINE ✦"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    stw = s_bbox[2] - s_bbox[0]
    draw.text((cx - stw // 2, by0 - 32), sub_text, font=sub_font, fill=(0, 240, 255, 240))

    return img

def build_fb_business_logo(master_img: Image.Image) -> Image.Image:
    """
    Product 2: AutoMovie Pro - FB Business Manager & Ad Automation Engine (৳2,999)
    Cyber Violet & Neon Magenta.
    Centerpiece: 3D Marketing Rocket & Target Reticle + Products Box.
    """
    img = recolor_master_badge(master_img, "magenta").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # Overlay high-tech vector graphics in center
    overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = 512, 460  # Center of badge

    # Draw circular dark inner backdrop for emblem contrast
    draw.ellipse([cx - 210, cy - 210, cx + 210, cy + 210], fill=(12, 8, 28, 220))
    # Concentric target reticle rings
    draw.ellipse([cx - 185, cy - 185, cx + 185, cy + 185], outline=(168, 85, 247, 180), width=3)
    draw.ellipse([cx - 130, cy - 130, cx + 130, cy + 130], outline=(236, 72, 153, 140), width=2)
    draw.ellipse([cx - 75, cy - 75, cx + 75, cy + 75], outline=(244, 63, 94, 120), width=2)

    # Crosshair ticks
    draw.line([cx - 195, cy, cx - 145, cy], fill=(236, 72, 153, 220), width=3)
    draw.line([cx + 145, cy, cx + 195, cy], fill=(236, 72, 153, 220), width=3)
    draw.line([cx, cy - 195, cx, cy - 145], fill=(236, 72, 153, 220), width=3)
    draw.line([cx, cy + 145, cx, cy + 195], fill=(236, 72, 153, 220), width=3)

    # 3D Launching Rocket / Growth Arrow Iconography
    # Rocket body
    rocket_poly = [
        (cx, cy - 130),       # Nose tip
        (cx + 42, cy - 40),   # Right shoulder
        (cx + 35, cy + 50),   # Right flank
        (cx + 65, cy + 85),   # Right fin tip
        (cx + 25, cy + 80),   # Right fin root
        (cx + 15, cy + 95),   # Right nozzle
        (cx - 15, cy + 95),   # Left nozzle
        (cx - 25, cy + 80),   # Left fin root
        (cx - 65, cy + 85),   # Left fin tip
        (cx - 35, cy + 50),   # Left flank
        (cx - 42, cy - 40),   # Left shoulder
    ]
    # Rocket glow
    draw.polygon(rocket_poly, fill=(245, 240, 255, 250), outline=(236, 72, 153, 255))
    
    # Rocket window
    draw.ellipse([cx - 18, cy - 35, cx + 18, cy + 1], fill=(168, 85, 247, 255), outline=(255, 255, 255, 240), width=3)
    draw.ellipse([cx - 10, cy - 27, cx + 10, cy - 7], fill=(0, 240, 255, 255))

    # Flame Exhaust
    flame_poly = [
        (cx - 15, cy + 96),
        (cx, cy + 160),
        (cx + 15, cy + 96),
        (cx + 8, cy + 115),
        (cx, cy + 130),
        (cx - 8, cy + 115)
    ]
    draw.polygon(flame_poly, fill=(255, 180, 0, 240))
    draw.polygon([(cx - 7, cy + 96), (cx, cy + 135), (cx + 7, cy + 96)], fill=(255, 255, 255, 255))

    # Dynamic Megaphone / Ad sparkles
    for angle_deg in [30, 45, 135, 150, -30, -45]:
        rad = math.radians(angle_deg)
        sx = cx + int(155 * math.cos(rad))
        sy = cy + int(155 * math.sin(rad))
        draw.line([sx - 8, sy, sx + 8, sy], fill=(244, 63, 94, 230), width=3)
        draw.line([sx, sy - 8, sx, sy + 8], fill=(244, 63, 94, 230), width=3)

    # Composite overlay onto recolored badge
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw bottom pill badge ribbon: "FB BUSINESS & ADS"
    badge_w, badge_h = 620, 84
    bx0, by0 = cx - badge_w // 2, int(1024 * 0.77)
    bx1, by1 = bx0 + badge_w, by0 + badge_h

    draw_pill_badge(draw, [bx0, by0, bx1, by1],
                    fill_color=(20, 8, 36, 245),
                    border_color=(236, 72, 153, 255),
                    glow_color=(168, 85, 247, 80),
                    border_width=4)

    # Text "FB BUSINESS & AD MANAGER"
    font = get_font(38)
    text = "FB BUSINESS & AD ENGINE"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2
    ty = by0 + (badge_h - th) // 2 - 4

    draw.text((tx + 2, ty + 2), text, font=font, fill=(40, 5, 50, 220))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Top mini label: "✦ CAMPAIGNS & REEL ADS ✦"
    sub_font = get_font(20)
    sub_text = "✦ AD CAMPAIGNS & PRODUCT STUDIO ✦"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    stw = s_bbox[2] - s_bbox[0]
    draw.text((cx - stw // 2, by0 - 32), sub_text, font=sub_font, fill=(236, 72, 153, 240))

    return img

def build_social_autopilot_logo(master_img: Image.Image) -> Image.Image:
    """
    Product 3: AutoMovie Pro - FB Profile & Page Post Automation Engine (৳1,999 / AutoSocial AI)
    Vivid Emerald Green & Cyber Teal.
    Centerpiece: Connected Social Graph Nodes + Lightning Bolt + Infinite Auto-Pilot Horizon.
    """
    img = recolor_master_badge(master_img, "emerald").resize((1024, 1024), Image.Resampling.LANCZOS)
    
    # Overlay high-tech vector graphics in center
    overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = 512, 460  # Center of badge

    # Dark inner circle
    draw.ellipse([cx - 210, cy - 210, cx + 210, cy + 210], fill=(6, 24, 20, 225))
    # Glowing rings
    draw.ellipse([cx - 185, cy - 185, cx + 185, cy + 185], outline=(16, 185, 129, 180), width=3)
    draw.ellipse([cx - 130, cy - 130, cx + 130, cy + 130], outline=(6, 182, 212, 140), width=2)

    # Social Network Nodes
    nodes = [
        (cx - 120, cy - 60),  # Node Left Top
        (cx + 120, cy - 60),  # Node Right Top
        (cx - 110, cy + 70),  # Node Left Bottom
        (cx + 110, cy + 70),  # Node Right Bottom
        (cx, cy - 130),       # Top Vertex
        (cx, cy + 110),       # Bottom Vertex
    ]
    # Draw circuit connections between nodes
    for nx, ny in nodes:
        draw.line([cx, cy, nx, ny], fill=(16, 185, 129, 160), width=3)
        for mx, my in nodes:
            dist = math.hypot(nx - mx, ny - my)
            if 100 < dist < 180:
                draw.line([nx, ny, mx, my], fill=(6, 182, 212, 90), width=2)

    # Draw nodes
    for i, (nx, ny) in enumerate(nodes):
        node_color = (16, 185, 129, 255) if i % 2 == 0 else (6, 182, 212, 255)
        draw.ellipse([nx - 18, ny - 18, nx + 18, ny + 18], fill=(4, 40, 32, 250), outline=node_color, width=3)
        draw.ellipse([nx - 8, ny - 8, nx + 8, ny + 8], fill=node_color)

    # Centerpiece: Auto-Pilot Lightning Bolt Emblem
    bolt_poly = [
        (cx + 10, cy - 90),
        (cx - 40, cy - 5),
        (cx - 5, cy - 5),
        (cx - 20, cy + 80),
        (cx + 45, cy - 5),
        (cx + 10, cy - 5),
    ]
    # Bolt glow & solid fill
    draw.polygon(bolt_poly, fill=(255, 255, 255, 255), outline=(16, 185, 129, 255))
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=(52, 211, 153, 180), width=2)

    # Composite overlay onto recolored badge
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw bottom pill badge ribbon: "SOCIAL PROFILE & PAGE AUTOPILOT"
    badge_w, badge_h = 640, 84
    bx0, by0 = cx - badge_w // 2, int(1024 * 0.77)
    bx1, by1 = bx0 + badge_w, by0 + badge_h

    draw_pill_badge(draw, [bx0, by0, bx1, by1],
                    fill_color=(4, 25, 20, 245),
                    border_color=(16, 185, 129, 255),
                    glow_color=(6, 182, 212, 80),
                    border_width=4)

    # Text "SOCIAL PROFILE & PAGE AUTOPILOT"
    font = get_font(36)
    text = "FB PROFILE & PAGE AUTOPILOT"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2
    ty = by0 + (badge_h - th) // 2 - 4

    draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 30, 20, 220))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Top mini label: "✦ 24/7 HUMAN-LIKE ORGANIC POSTING ✦"
    sub_font = get_font(19)
    sub_text = "✦ 24/7 HUMAN-LIKE SOCIAL POSTER ✦"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    stw = s_bbox[2] - s_bbox[0]
    draw.text((cx - stw // 2, by0 - 32), sub_text, font=sub_font, fill=(52, 211, 153, 240))

    return img

def build_whatsapp_marketing_logo(master_img: Image.Image) -> Image.Image:
    """
    Product 4: WAManager Pro — WhatsApp Marketing & CRM Suite (৳999/৳1,999)
    WhatsApp Emerald Green & Cyber Teal.
    Centerpiece: 3D WhatsApp Chat Bubble with Phone, Dynamic Broadcast Waves & Anti-Ban Shield.
    """
    img = recolor_master_badge(master_img, "emerald").resize((1024, 1024), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = 512, 455

    # Dark inner circle
    draw.ellipse([cx - 210, cy - 210, cx + 210, cy + 210], fill=(4, 28, 18, 235))
    # Glowing cyber circles
    draw.ellipse([cx - 188, cy - 188, cx + 188, cy + 188], outline=(37, 211, 102, 190), width=3)
    draw.ellipse([cx - 135, cy - 135, cx + 135, cy + 135], outline=(18, 140, 126, 150), width=2)

    # 3D Chat Bubble with Tail
    bubble_r = 100
    bubble_cx, bubble_cy = cx - 5, cy - 10
    draw.ellipse([bubble_cx - bubble_r, bubble_cy - bubble_r, bubble_cx + bubble_r, bubble_cy + bubble_r],
                 fill=(18, 140, 126, 245), outline=(37, 211, 102, 255), width=5)
    
    # Bubble pointer tail (bottom-left)
    tail_poly = [
        (bubble_cx - 50, bubble_cy + 75),
        (bubble_cx - 95, bubble_cy + 120),
        (bubble_cx - 15, bubble_cy + 95)
    ]
    draw.polygon(tail_poly, fill=(18, 140, 126, 245), outline=(37, 211, 102, 255))
    # Fill seam
    draw.ellipse([bubble_cx - bubble_r + 4, bubble_cy - bubble_r + 4, bubble_cx + bubble_r - 4, bubble_cy + bubble_r - 4],
                 fill=(37, 211, 102, 245))

    # Inner WhatsApp Phone Icon silhouette
    phone_color = (255, 255, 255, 255)
    # Curved handset representation
    draw.arc([bubble_cx - 55, bubble_cy - 55, bubble_cx + 55, bubble_cy + 55], start=45, end=225, fill=phone_color, width=16)
    # Earpiece & Mouthpiece
    draw.ellipse([bubble_cx - 55, bubble_cy - 20, bubble_cx - 25, bubble_cy + 15], fill=phone_color)
    draw.ellipse([bubble_cx + 20, bubble_cy + 25, bubble_cx + 52, bubble_cy + 60], fill=phone_color)

    # Broadcast signal waves radiating outward top-right
    for dist, w, alpha in [(125, 4, 210), (150, 3, 160), (175, 2, 110)]:
        bbox = [bubble_cx - dist + 60, bubble_cy - dist - 40, bubble_cx + dist + 60, bubble_cy + dist - 40]
        draw.arc(bbox, start=300, end=350, fill=(37, 211, 102, alpha), width=w)

    # Composite overlay
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw bottom pill badge ribbon: "WHATSAPP MARKETING SUITE"
    badge_w, badge_h = 620, 84
    bx0, by0 = cx - badge_w // 2, int(1024 * 0.77)
    bx1, by1 = bx0 + badge_w, by0 + badge_h

    draw_pill_badge(draw, [bx0, by0, bx1, by1],
                    fill_color=(4, 28, 18, 245),
                    border_color=(37, 211, 102, 255),
                    glow_color=(18, 140, 126, 90),
                    border_width=4)

    # Text "WHATSAPP MARKETING SUITE"
    font = get_font(36)
    text = "WHATSAPP MARKETING SUITE"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2
    ty = by0 + (badge_h - th) // 2 - 4

    draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 25, 15, 220))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Top mini label: "✦ BULK BROADCAST & 24/7 AI BOT ✦"
    sub_font = get_font(19)
    sub_text = "✦ BULK BROADCAST & 24/7 AI BOT ✦"
    s_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    stw = s_bbox[2] - s_bbox[0]
    draw.text((cx - stw // 2, by0 - 32), sub_text, font=sub_font, fill=(37, 211, 102, 240))

    return img

def main():
    print("[LOGO GENERATOR] Loading master logo:", MASTER_LOGO_PATH)
    master_img = Image.open(MASTER_LOGO_PATH).convert("RGBA")

    print("[LOGO GENERATOR] Creating Product 1: Video Content Studio...")
    p1 = build_video_studio_logo(master_img)
    
    print("[LOGO GENERATOR] Creating Product 2: FB Business Manager & Ad Engine...")
    p2 = build_fb_business_logo(master_img)
    
    print("[LOGO GENERATOR] Creating Product 3: Social AutoPilot Engine...")
    p3 = build_social_autopilot_logo(master_img)

    print("[LOGO GENERATOR] Creating Product 4: WhatsApp Marketing Suite...")
    p4 = build_whatsapp_marketing_logo(master_img)

    products = [
        ("logo_video_studio.png", p1),
        ("logo_fb_business.png", p2),
        ("logo_profile_page.png", p3),
        ("logo_wa_marketing.png", p4),
    ]

    # Save to AutoMoviePro-Website/assets/img/
    for fn, img in products:
        out_p = os.path.join(WEBSITE_IMG_DIR, fn)
        img.save(out_p, "PNG")
        print(f" -> Saved to Website: {out_p} ({img.size})")

        # Also save 512, 256, 128
        base_name = fn.replace(".png", "")
        for sz in [512, 256, 128]:
            resized = img.resize((sz, sz), Image.Resampling.LANCZOS)
            resized.save(os.path.join(WEBSITE_IMG_DIR, f"{base_name}-{sz}.png"), "PNG")

    # Save to AutoMoviePro-Software/ui/img/
    p1.save(os.path.join(SOFTWARE_IMG_DIR, "logo-video-studio.png"), "PNG")
    master_img.resize((192, 192), Image.Resampling.LANCZOS).save(os.path.join(SOFTWARE_IMG_DIR, "logo-header.png"), "PNG")
    master_img.resize((384, 384), Image.Resampling.LANCZOS).save(os.path.join(SOFTWARE_IMG_DIR, "logo-login.png"), "PNG")
    master_img.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(SOFTWARE_IMG_DIR, "logo-sm.png"), "PNG")
    p2.save(os.path.join(SOFTWARE_IMG_DIR, "logo-fb-business.png"), "PNG")
    p3.save(os.path.join(SOFTWARE_IMG_DIR, "logo-social-autopilot.png"), "PNG")
    print(f" -> Saved to AutoMoviePro-Software/ui/img/")

    # Save to Socialmedia_Maneger/static/img/
    p2.save(os.path.join(SOCIAL_MANAGER_IMG_DIR, "logo_fb_business.png"), "PNG")
    p3.save(os.path.join(SOCIAL_MANAGER_IMG_DIR, "logo_profile_page.png"), "PNG")
    master_img.resize((256, 256), Image.Resampling.LANCZOS).save(os.path.join(SOCIAL_MANAGER_IMG_DIR, "logo.png"), "PNG")
    print(f" -> Saved to Socialmedia_Maneger/static/img/")

    # Save to E:\AI Assistant\Automations\
    master_img.save(os.path.join(AUTOMATIONS_DIR, "logo_automovie_master.png"), "PNG")
    p1.save(os.path.join(AUTOMATIONS_DIR, "logo_video_studio.png"), "PNG")
    p2.save(os.path.join(AUTOMATIONS_DIR, "logo_fb_business.png"), "PNG")
    p3.save(os.path.join(AUTOMATIONS_DIR, "logo_profile_page.png"), "PNG")
    print(f" -> Saved to E:\\AI Assistant\\Automations\\")

    print("[LOGO GENERATOR] All distinct product logos successfully created and distributed!")

if __name__ == "__main__":
    main()
