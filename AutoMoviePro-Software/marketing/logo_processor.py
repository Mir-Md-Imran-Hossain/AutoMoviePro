"""
=============================================================================
Universal Logo Processor & Core Aesthetic Isolator
=============================================================================
Solves the logo presentation problem across all social media banners,
profiles, and posts for As-Sunnah Path, AutoMovie Pro, and future brands.

Specifically adheres to user aesthetic requirement:
'লোগোর ব্যাকগ্রাউন্ড নিয়ে চিন্তা করার দরকার নেই লোগর মূল অংশটি ব্যবহার করলেই
হবে পোষ্টের মধ্যে বা ইমেজের মধ্যে অথবা ব্যানারের মধ্যে, সরাসরি ফাইলে থাকা
নির্দিষ্ট লোগোটি জোর করে বসিয়ে ব্যানারটি দেখতে খারাপ লাগবে এরকম যেন না হয়
তাই ব্যাকগ্রাউন্ড লোগোর মূল অংশগুলো যেন সঠিক জায়গায় বসানো থাকে, এটা শুধুমাত্র
এই ক্ষেত্রেই সকল পেইজ এবং সকল প্রোফাইলের যতগুলো ইমেজ ব্যানার তৈরি হবে তার
প্রত্যেকটির ক্ষেত্রে এই পদ্ধতিটি কাজে লাগাতে হবে'

Core Features:
1. Eliminates solid, dark, white, and spotlight/glow backgrounds from logo files.
2. Extracts pure core emblem / iconography / typography with crisp anti-aliasing.
3. Automatically crops to tight symmetric square or natural bounds.
4. Preserves color saturation and alpha gradients (no harsh jagged outlines).
5. Provides universal auto-keying for future brands (dark/light/gradient backdrops).
=============================================================================
"""

import os
import cv2
import numpy as np
from PIL import Image

BASE_DIR = r"E:\AI Assistant"
LOGOS_DIR = os.path.join(BASE_DIR, "Content", "image", "Logos")
AUTOMATIONS_DIR = os.path.join(BASE_DIR, "Automations")

ASSUNNAH_DIR = os.path.join(LOGOS_DIR, "As-Sunnah_Path_Logo(All_Language)")
AUTOMOVIE_DIR = os.path.join(LOGOS_DIR, "Automovie Pro Logo & Cover Photo")


def isolate_assunnah_emblem(
    input_path: str = None,
    output_path: str = None,
    mode: str = "emblem",
    padding_pct: float = 0.05
) -> Image.Image:
    """
    Isolates the authentic golden Islamic emblem from the As-Sunnah Path logo.
    Eliminates the dark background canvas and the top-left spotlight/glow.
    
    Modes:
      - 'emblem': Pure circular/ornate Islamic dome & crescent emblem (ideal for headers).
      - 'full': Full emblem + typography text with transparent background.
    """
    if input_path is None:
        input_path = os.path.join(ASSUNNAH_DIR, "As-Sunnah_Path_Logo.png")
    if output_path is None:
        suffix = "_emblem" if mode == "emblem" else "_full"
        output_path = os.path.join(AUTOMATIONS_DIR, f"logo_assunnah{suffix}.png")

    img = Image.open(input_path).convert("RGB")
    arr = np.array(img).astype(np.float32)
    h, w, _ = arr.shape

    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    # Gold Chromatic Metric:
    # Golden pixels have high R and G, low B: (R + G) / 2 - B is strongly positive.
    # The background spotlight in the top-left is lavender/cool-white: B is high, R & G are equal or lower.
    goldness = (r * 0.5 + g * 0.5) - b
    warm_condition = (r > b + 6.0) & (g > b + 4.0) & (g > 25.0)

    # Compute soft alpha gradient for smooth anti-aliased edges
    alpha = np.zeros((h, w), dtype=np.float32)
    # Smoothstep ramp between 6.0 and 30.0 goldness
    ramp = np.clip((goldness - 6.0) / 24.0, 0.0, 1.0)
    alpha[warm_condition] = ramp[warm_condition]

    if mode == "emblem":
        # The emblem occupies the upper section (y roughly 35..370, x roughly 100..400)
        # Separated cleanly from text which begins around y=380
        emblem_mask = alpha.copy()
        emblem_mask[370:, :] = 0.0  # Cut off bottom text to isolate core emblem

        ys, xs = np.where(emblem_mask > 0.1)
        if len(ys) == 0:
            raise ValueError("No emblem pixels detected!")
        
        y_min, y_max = ys.min(), ys.max()
        x_min, x_max = xs.min(), xs.max()

        crop_arr = arr[y_min:y_max + 1, x_min:x_max + 1]
        crop_alpha = emblem_mask[y_min:y_max + 1, x_min:x_max + 1]

        crop_h = y_max - y_min + 1
        crop_w = x_max - x_min + 1
        max_dim = max(crop_h, crop_w)
        pad = int(max_dim * padding_pct)
        target_size = max_dim + 2 * pad

        square_rgba = np.zeros((target_size, target_size, 4), dtype=np.uint8)
        off_y = (target_size - crop_h) // 2
        off_x = (target_size - crop_w) // 2

        square_rgba[off_y:off_y + crop_h, off_x:off_x + crop_w, :3] = crop_arr.astype(np.uint8)
        
        # Anti-aliased alpha smoothing
        alpha_u8 = (crop_alpha * 255.0).astype(np.uint8)
        alpha_smooth = cv2.GaussianBlur(alpha_u8, (3, 3), 0.5)
        square_rgba[off_y:off_y + crop_h, off_x:off_x + crop_w, 3] = alpha_smooth

        result = Image.fromarray(square_rgba, "RGBA")

    else:
        # Full mode: Emblem + Text
        ys, xs = np.where(alpha > 0.1)
        y_min, y_max = ys.min(), ys.max()
        x_min, x_max = xs.min(), xs.max()

        crop_arr = arr[y_min:y_max + 1, x_min:x_max + 1]
        crop_alpha = alpha[y_min:y_max + 1, x_min:x_max + 1]

        crop_h = y_max - y_min + 1
        crop_w = x_max - x_min + 1
        pad_y = int(crop_h * padding_pct)
        pad_x = int(crop_w * padding_pct)

        full_rgba = np.zeros((crop_h + 2 * pad_y, crop_w + 2 * pad_x, 4), dtype=np.uint8)
        full_rgba[pad_y:pad_y + crop_h, pad_x:pad_x + crop_w, :3] = crop_arr.astype(np.uint8)
        
        alpha_u8 = (crop_alpha * 255.0).astype(np.uint8)
        alpha_smooth = cv2.GaussianBlur(alpha_u8, (3, 3), 0.5)
        full_rgba[pad_y:pad_y + crop_h, pad_x:pad_x + crop_w, 3] = alpha_smooth

        result = Image.fromarray(full_rgba, "RGBA")

    result.save(output_path, "PNG")
    print(f"[LOGO PROCESSOR] As-Sunnah ({mode}) saved: {output_path} ({result.size})")
    return result


def isolate_automovie_logo(
    input_path: str = None,
    output_path: str = None,
    mode: str = "badge",
    padding_pct: float = 0.03
) -> Image.Image:
    """
    Isolates the official AutoMovie Pro logo.
    
    Modes:
      - 'badge': Circular 3D cinematic emblem with smooth anti-aliased transparency
                 (removes the solid white square canvas).
      - 'core_mark': Pure neon camera iconography + typography (removes dark backdrop).
    """
    if input_path is None:
        input_path = os.path.join(AUTOMOVIE_DIR, "AutoMovie Pro Cinematic Logo.png")
    if output_path is None:
        output_path = os.path.join(AUTOMATIONS_DIR, f"logo_automovie_{mode}.png")

    img = Image.open(input_path).convert("RGB")
    arr = np.array(img).astype(np.float32)
    h, w, _ = arr.shape

    # Find the circular badge center and radius
    # Non-white pixels (where R, G, B are not all > 240)
    non_white = ~((arr[:, :, 0] > 240) & (arr[:, :, 1] > 240) & (arr[:, :, 2] > 240))
    ys, xs = np.where(non_white)
    cy = (ys.min() + ys.max()) / 2.0
    cx = (xs.min() + xs.max()) / 2.0
    radius = (xs.max() - xs.min()) / 2.0

    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx)**2 + (Y - cy)**2)

    if mode == "badge":
        # Smooth anti-aliased circular alpha cutoff removing white canvas
        # Inner radius cutoff ~ radius - 1.5px
        alpha = np.clip((radius - 1.0 - dist) / 1.5, 0.0, 1.0)
        
        # Crop tightly to the circle with slight breathing room
        y_min = max(0, int(cy - radius - 2))
        y_max = min(h, int(cy + radius + 3))
        x_min = max(0, int(cx - radius - 2))
        x_max = min(w, int(cx + radius + 3))

        crop_arr = arr[y_min:y_max, x_min:x_max]
        crop_alpha = alpha[y_min:y_max, x_min:x_max]

        rgba = np.dstack([crop_arr.astype(np.uint8), (crop_alpha * 255.0).astype(np.uint8)])
        result = Image.fromarray(rgba, "RGBA")

    elif mode == "core_mark":
        # Extract pure neon cyan & typography from inside the badge
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        diff = np.maximum(np.maximum(np.abs(r - g), np.abs(r - b)), np.abs(g - b))

        inside_badge = dist < (radius - 10.0)
        score = np.maximum((lum - 35.0) / 50.0, (diff - 20.0) / 30.0)
        score = np.clip(score, 0.0, 1.0)

        alpha = np.zeros((h, w), dtype=np.float32)
        alpha[inside_badge] = score[inside_badge]

        ys_m, xs_m = np.where(alpha > 0.15)
        y_min, y_max = ys_m.min(), ys_m.max()
        x_min, x_max = xs_m.min(), xs_m.max()

        crop_arr = arr[y_min:y_max + 1, x_min:x_max + 1]
        crop_alpha = alpha[y_min:y_max + 1, x_min:x_max + 1]

        crop_h = y_max - y_min + 1
        crop_w = x_max - x_min + 1
        max_dim = max(crop_h, crop_w)
        pad = int(max_dim * padding_pct)
        target_size = max_dim + 2 * pad

        square_rgba = np.zeros((target_size, target_size, 4), dtype=np.uint8)
        off_y = (target_size - crop_h) // 2
        off_x = (target_size - crop_w) // 2

        square_rgba[off_y:off_y + crop_h, off_x:off_x + crop_w, :3] = crop_arr.astype(np.uint8)
        
        alpha_u8 = (crop_alpha * 255.0).astype(np.uint8)
        alpha_smooth = cv2.GaussianBlur(alpha_u8, (3, 3), 0.5)
        square_rgba[off_y:off_y + crop_h, off_x:off_x + crop_w, 3] = alpha_smooth

        result = Image.fromarray(square_rgba, "RGBA")

    result.save(output_path, "PNG")
    print(f"[LOGO PROCESSOR] AutoMovie Pro ({mode}) saved: {output_path} ({result.size})")
    return result


def auto_isolate_core_logo(image_path: str, output_path: str) -> Image.Image:
    """
    Universal isolator for ANY future brand logo.
    Detects canvas backdrop (solid white, dark, or transparent)
    and removes outer square frames so the core mark floats naturally.
    """
    img = Image.open(image_path)
    if img.mode == "RGBA":
        arr = np.array(img)
        # Already transparent, just tighten bounding box
        alpha = arr[:, :, 3]
        if alpha.min() < 250:
            ys, xs = np.where(alpha > 10)
            if len(ys) > 0:
                crop = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
                crop.save(output_path, "PNG")
                return crop

    # Inspect corners to identify background color
    rgb = img.convert("RGB")
    arr = np.array(rgb).astype(np.float32)
    h, w, _ = arr.shape
    corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]])
    bg_color = np.median(corners, axis=0)

    # Color difference from background
    color_diff = np.sqrt(np.sum((arr - bg_color) ** 2, axis=2))
    
    # Smooth thresholding
    threshold_low = 25.0
    threshold_high = 60.0
    alpha = np.clip((color_diff - threshold_low) / (threshold_high - threshold_low), 0.0, 1.0)
    
    alpha_u8 = (alpha * 255.0).astype(np.uint8)
    alpha_smooth = cv2.GaussianBlur(alpha_u8, (3, 3), 0.5)

    ys, xs = np.where(alpha_smooth > 20)
    if len(ys) == 0:
        # Fallback to original
        rgb.save(output_path, "PNG")
        return rgb

    y_min, y_max = ys.min(), ys.max()
    x_min, x_max = xs.min(), xs.max()

    crop_arr = arr[y_min:y_max + 1, x_min:x_max + 1].astype(np.uint8)
    crop_alpha = alpha_smooth[y_min:y_max + 1, x_min:x_max + 1]

    rgba = np.dstack([crop_arr, crop_alpha])
    result = Image.fromarray(rgba, "RGBA")
    result.save(output_path, "PNG")
    print(f"[LOGO PROCESSOR] Universal isolation saved: {output_path} ({result.size})")
    return result


def process_all_brand_logos():
    """
    Processes all standard logos for As-Sunnah Path and AutoMovie Pro,
    generating production-ready transparent emblems and marks.
    """
    print("\n" + "=" * 60)
    print("RUNNING MASTER LOGO PROCESSOR (AESTHETIC ISOLATION)")
    print("=" * 60)

    # 1. As-Sunnah Path Core Emblem
    as_emblem_path = os.path.join(AUTOMATIONS_DIR, "logo_assunnah_transparent.png")
    isolate_assunnah_emblem(mode="emblem", output_path=as_emblem_path)

    # 2. Overwrite default logo_assunnah.png so all legacy references become transparent
    default_assunnah = os.path.join(AUTOMATIONS_DIR, "logo_assunnah.png")
    isolate_assunnah_emblem(mode="emblem", output_path=default_assunnah)

    # 3. As-Sunnah Full (Emblem + Typography)
    as_full_path = os.path.join(AUTOMATIONS_DIR, "logo_assunnah_full_transparent.png")
    isolate_assunnah_emblem(mode="full", output_path=as_full_path)

    # 4. AutoMovie Pro Circular Cinematic Badge (Pure Transparent Outside)
    am_badge_path = os.path.join(AUTOMATIONS_DIR, "logo_automovie_transparent.png")
    isolate_automovie_logo(mode="badge", output_path=am_badge_path)

    # 5. AutoMovie Pro Default
    default_automovie = os.path.join(AUTOMATIONS_DIR, "logo_automovie.png")
    isolate_automovie_logo(mode="badge", output_path=default_automovie)

    # 6. AutoMovie Pro Core Mark (Cyber Neon Iconography)
    am_mark_path = os.path.join(AUTOMATIONS_DIR, "logo_automovie_core_mark.png")
    isolate_automovie_logo(mode="core_mark", output_path=am_mark_path)

    print("=" * 60)
    print("ALL BRAND LOGOS ISOLATED AND SAVED SUCCESSFULLY!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    process_all_brand_logos()
