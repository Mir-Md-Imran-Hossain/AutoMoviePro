"""
=============================================================================
OmniSocial AI - Dynamic Product Catalog & Multi-Product Automation Engine
=============================================================================
Centralized Product Management & Video Ad Production Orchestrator:
1. Product Catalog:
   - Full CRUD operations: Add / Edit / List / Delete products.
   - Comprehensive metadata: Name, Category, Description, Key Features,
     Regular & Offer Price (BDT / USD), Contact Info (WhatsApp, Phone, Email,
     Website, Socials), Logo/Image assets, Target Audience, Tone of Voice.
   - Automation switches: Banner Generation, Written Posts, Video Ads.
2. Content Generation Engines:
   - Dynamic Branded Promotional Banners (Pillow based, high-converting).
   - High-Converting Written Social Posts & Copywriting generator.
   - Ad Video Storyboard and Video Ad Compilation via OmniAdStudioGenerator.
3. Vault & Ad Storage:
   - Saves compiled ads and metadata to `E:\\AI Assistant\\Social Media Hub\\product_ads_vault`.
   - Ad Status lifecycle: draft, approved, scheduled, published.
=============================================================================
"""

import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import json
import time
import uuid
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HUB_DIR = Path(r"E:\AI Assistant\Social Media Hub")
CATALOG_FILE = HUB_DIR / "products_catalog.json"
VAULT_DIR = HUB_DIR / "product_ads_vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)
BANNERS_DIR = HUB_DIR / "product_banners"
BANNERS_DIR.mkdir(parents=True, exist_ok=True)

# Common fonts
FONTS_DIR = Path(r"C:\Windows\Fonts")


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Tries to find clear unicode fonts supporting Bengali / English."""
    candidates = [
        "kalpurush.ttf", "Siyamrupali.ttf", "vrinda.ttf", "SolaimanLipi.ttf",
        "seguiemj.ttf", "segoeui.ttf", "arial.ttf"
    ]
    if bold:
        candidates = ["segoeuib.ttf", "arialbd.ttf"] + candidates

    for name in candidates:
        fp = FONTS_DIR / name
        if fp.exists():
            try:
                return ImageFont.truetype(str(fp), size)
            except Exception:
                continue
    return ImageFont.load_default()


class OmniProductManager:
    """Industrial-grade Product Manager & Multi-Product Content Generator."""

    @classmethod
    def load_catalog(cls) -> List[Dict[str, Any]]:
        """Loads all products from the JSON catalog."""
        if not CATALOG_FILE.exists():
            cls._seed_default_catalog()
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "products" in data:
                    return data["products"]
        except Exception as e:
            print(f"[OmniProductManager] Warning: Error reading catalog ({e}), returning default seed.", flush=True)
            cls._seed_default_catalog()
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    @classmethod
    def save_catalog(cls, products: List[Dict[str, Any]]) -> bool:
        """Atomically saves products catalog."""
        temp_file = CATALOG_FILE.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            temp_file.replace(CATALOG_FILE)
            return True
        except Exception as e:
            print(f"[OmniProductManager] Error saving catalog: {e}", flush=True)
            if temp_file.exists():
                temp_file.unlink()
            return False

    @classmethod
    def _seed_default_catalog(cls):
        """Seeds all 4 flagship products (Video Studio, FB Business, FB Profile, WhatsApp Suite)."""
        default_products = [
            {
                "id": "video_studio",
                "slug": "automovie-pro-suite",
                "name": "AutoMovie Pro - Social Media Content Automation Engine",
                "short_name": "ফুল ভিডিও স্টুডিও (Full Video Studio)",
                "category": "AI Video Production & Multi-Channel Studio",
                "badge": "🎬 ফুল কন্টেন্ট পাওয়ারহাউজ",
                "description": "সম্পূর্ণ স্বয়ংক্রিয় এআই ভিডিও ও সোশ্যাল মিডিয়া পাওয়ারহাউজ। ক্যামেরা বা এডিটর ছাড়াই ভাইরাল শর্টস, ৫ মিনিটের লং ভিডিও ও বহুভাষিক ডাবিংয়ের স্বয়ংক্রিয় প্রোডাকশন ইঞ্জিন।",
                "features": [
                    "১০০% স্বয়ংক্রিয় এআই ভিডিও তৈরি (শর্টস ও ৫ মিনিটের সিনেমাটিক লং ভিডিও)",
                    "৩য় অতিরিক্ত আন্তর্জাতিক ভাষা সম্পূর্ণ ফ্রি (হিন্দি/উর্দু/ইংরেজি আজীবন ফ্রি)",
                    "৩টি ফেসবুক, ৩টি ইউটিউব ও ৩টি টিকটক (৯টি প্ল্যাটফর্মে একসাথে) ভিডিও পোস্ট করে ট্রিপল প্যাসিভ ইনকাম",
                    "খাঁটি বাংলা ও ৬০+ আন্তর্জাতিক ভাষায় মানুষের মতো ন্যাচারাল ভয়েসওভার",
                    "ট্রেন্ডিং ভাইরাল টপিক রিসার্চ ও ডিপ ইমোশনাল সিনেমাটিক চিত্রনাট্য",
                    "আল্ট্রা-এইচডি সিনেমাটিক ফুটেজ, কেন-বার্নস মোশন ও কাইনেটিক সাবটাইটেল",
                    "এককালীন মাত্র ৩,৯৯৯ টাকায় আজীবন লাইসেন্স — কোনো মাসিক বা বাৎসরিক ফি নেই",
                    "লাইফটাইম লাইসেন্স — কোনো মাসিক বা বাৎসরিক ফি নেই (আর মাত্র ৮-১০ দিন কার্যকর)"
                ],
                "regular_price": "৳১০,০০০",
                "offer_price": "৳৩,৯৯৯",
                "price_num": 3999,
                "currency": "BDT",
                "billing_type": "One-Time Lifetime Deal",
                "contact_info": {
                    "phone": "+8801968111593",
                    "whatsapp": "+8801968111593",
                    "whatsapp_link": "https://wa.me/8801968111593",
                    "email": "support@automoviepro.com",
                    "website": "https://automoviepro.com",
                    "social_handles": {
                        "facebook": "https://facebook.com/automoviepro",
                        "youtube": "https://youtube.com/@automoviepro"
                    }
                },
                "logo_or_image": "",
                "target_audience": "Content Creators, Freelancers, Digital Marketers, YouTube Channel Owners, Media Agencies",
                "tone_of_voice": "Energetic, Cinematic, Visionary, Premium",
                "auto_campaign_settings": {
                    "enable_banners": True,
                    "enable_written_posts": True,
                    "enable_video_ads": True,
                    "post_frequency": "1 per day"
                },
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "id": "fb_business",
                "slug": "omni-fb-business-manager",
                "name": "AutoMovie Pro - FB Business Manager & Ad Automation Engine",
                "short_name": "বিজনেস ও সেলস ম্যানেজার (FB Business Manager)",
                "category": "F-Commerce, Business Sales & Ad Automation",
                "badge": "💼 বিজনেস ও সেলস ম্যানেজার",
                "description": "ফেসবুক বিজনেস পেজ সেলস, কাইনেটিক বিজ্ঞাপন ও টার্গেটেড অর্গানিক গ্রুপ শেয়ারিং অটোমেশন। পেজ পরিচালনা ও কাস্টমার এনগেজমেন্টের ফুল অটো-পাইলট।",
                "features": [
                    "ব্যবসার ফেসবুক পেজে ২৪/৭ স্বয়ংক্রিয় পোস্টিং ও সম্পূর্ণ অটো-পাইলট",
                    "প্রোডাক্টের জন্য আকর্ষণীয় হাই-কনভার্টিং সেলস ব্যানার ও অফার গ্রাফিক্স",
                    "৩০ থেকে ৭০ সেকেন্ডের ভাইরাল কাইনেটিক সেলস বিজ্ঞাপন ভিডিও তৈরি",
                    "ফেসবুক অ্যাড খরচ ছাড়া টার্গেটেড ফেসবুক গ্রুপে নিরাপদ অর্গানিক শেয়ারিং",
                    "মেসেঞ্জারে ২৪/৭ সেলস রিপ্লাই, কাস্টমার এনগেজমেন্ট ও লিড ম্যানেজমেন্ট",
                    "স্প্যাম ও নেগেটিভ কমেন্ট স্বয়ংক্রিয় ফিল্টারিং ও হাইড প্রটেকশন",
                    "লাইফটাইম লাইসেন্স — কোনো মাসিক চার্জ নেই"
                ],
                "regular_price": "৳৮,৫০০",
                "offer_price": "৳২,৯৯৯",
                "price_num": 2999,
                "currency": "BDT",
                "billing_type": "One-Time Lifetime Deal",
                "contact_info": {
                    "phone": "+8801968111593",
                    "whatsapp": "+8801968111593",
                    "whatsapp_link": "https://wa.me/8801968111593",
                    "email": "business@automoviepro.com",
                    "website": "https://automoviepro.com",
                    "social_handles": {
                        "facebook": "https://facebook.com/automoviepro"
                    }
                },
                "logo_or_image": "",
                "target_audience": "F-commerce Shop Owners, Agency Founders, Small Business Entrepreneurs, Online Sellers",
                "tone_of_voice": "Professional, Value-Driven, Urgent, Commercial",
                "auto_campaign_settings": {
                    "enable_banners": True,
                    "enable_written_posts": True,
                    "enable_video_ads": True,
                    "post_frequency": "1 per day"
                },
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "id": "profile_page",
                "slug": "omni-fb-profile-page",
                "name": "AutoMovie Pro - FB Profile & Page Post Automation Engine",
                "short_name": "প্রোফাইল ও পেজ অটো-পাইলট (FB Profile & Page)",
                "category": "Personal Branding & Organic Post Automation",
                "badge": "📱 প্রোফাইল ও পেজ অটো-পাইলট",
                "description": "ব্যক্তিগত ফেসবুক প্রোফাইল ও পেজের জন্য স্বয়ংক্রিয় পোস্ট ও ব্র্যান্ডিং। ইসলামিক হাদিস, মোটিভেশনাল উক্তি, শিক্ষণীয় কন্টেন্ট ও টার্গেটেড অর্গানিক গ্রুপ শেয়ারিং।",
                "features": [
                    "ব্যক্তিগত ফেসবুক প্রোফাইল ও পেজের জন্য স্বয়ংক্রিয় পোস্ট ও ব্র্যান্ডিং",
                    "ইসলামিক হাদিস, মোটিভেশনাল উক্তি ও তথ্যবহুল কোট ব্যানার তৈরি",
                    "মানুষের মতো স্বাভাবিক অনুভূতির আবেগঘন ক্যাপশন ও স্ট্যাটাস ড্রাফটিং",
                    "১০০% মানুষের মতো র্যান্ডম মাউস মুভমেন্ট ও অ্যান্টি-ব্যান সেফ ইন্টারভাল",
                    "টাইমলাইন এবং বিভিন্ন পাবলিক গ্রুপে নিরাপদ অর্গানিক পোস্ট শেয়ারিং",
                    "ডেইলি শিডিউল অনুযায়ী অটোমেশন — প্রোফাইল সার্বক্ষণিক সচল",
                    "আজীবন লাইসেন্স — জিরো রিনিউয়াল ফি"
                ],
                "regular_price": "৳৫,৫০০",
                "offer_price": "৳১,৯৯৯",
                "price_num": 1999,
                "currency": "BDT",
                "billing_type": "One-Time Lifetime Deal",
                "contact_info": {
                    "phone": "+8801968111593",
                    "whatsapp": "+8801968111593",
                    "whatsapp_link": "https://wa.me/8801968111593",
                    "email": "profile@automoviepro.com",
                    "website": "https://automoviepro.com",
                    "social_handles": {
                        "facebook": "https://facebook.com/automoviepro"
                    }
                },
                "logo_or_image": "",
                "target_audience": "Individual Professionals, Influencers, Public Figures, Islamic Page Admins",
                "tone_of_voice": "Inspirational, Respectful, Thoughtful, Authentic",
                "auto_campaign_settings": {
                    "enable_banners": True,
                    "enable_written_posts": True,
                    "enable_video_ads": True,
                    "post_frequency": "1 per day"
                },
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "id": "wa_marketing",
                "slug": "wamanager-pro-suite",
                "name": "WAManager Pro — WhatsApp Marketing Suite",
                "short_name": "হোয়াটসঅ্যাপ মার্কেটিং স্যুট (WhatsApp Suite)",
                "category": "WhatsApp Marketing, Bulk Messaging & Lead Scraping",
                "badge": "📱 WhatsApp মার্কেটিং পাওয়ারহাউজ",
                "description": "আনলিমিটেড বাল্ক মেসেজিং, অ্যান্টি-ব্যান স্পিনট্যাক্স, অটো-রিপ্লাই বট ও গুগল ম্যাপস/বি২বি লিড স্ক্র্যাপার সহ সম্পূর্ণ হোয়াটসঅ্যাপ মার্কেটিং সমাধান।",
                "features": [
                    "আনলিমিটেড বাল্ক মেসেজিং — এক ক্লিকে হাজার হাজার নাম্বারে মেসেজ প্রেরণ",
                    "অ্যাকাউন্ট সুরক্ষায় শক্তিশালী অ্যান্টি-ব্যান স্পিনট্যাক্স ও র্যান্ডম ডিলে",
                    "২৪/৭ স্বয়ংক্রিয় চ্যাটবট ও ইন্টেলিজেন্ট অটো-রিপ্লাই সিস্টেম",
                    "গুগল ম্যাপস ও বি২বি ডিরেক্টরি থেকে টার্গেটেড কাস্টমার নাম্বার স্ক্র্যাপার",
                    "নম্বর ফিল্টার — অ্যাক্টিভ WhatsApp নম্বর স্বয়ংক্রিয় যাচাই",
                    "শিডিউলড ড্রিপ ক্যাম্পেইন ও রিয়েল-টাইম ডেলিভারি অ্যানালিটিক্স রিপোর্ট",
                    "১ বছর লাইসেন্স + সার্বক্ষণিক সাপোর্ট ও নিয়মিত ফিচার আপডেট"
                ],
                "regular_price": "৳২,৯৯৯",
                "offer_price": "৳৯৯৯",
                "price_num": 999,
                "currency": "BDT",
                "billing_type": "1-Year Subscription Deal",
                "contact_info": {
                    "phone": "+8801968111593",
                    "whatsapp": "+8801968111593",
                    "whatsapp_link": "https://wa.me/8801968111593",
                    "email": "wamanager@automoviepro.com",
                    "website": "https://automoviepro.com",
                    "social_handles": {
                        "facebook": "https://facebook.com/automoviepro"
                    }
                },
                "logo_or_image": "",
                "target_audience": "Digital Marketers, Lead Generation Agencies, B2B Businesses, F-commerce Sellers",
                "tone_of_voice": "Direct, High-Utility, High-ROI, Action-Oriented",
                "auto_campaign_settings": {
                    "enable_banners": True,
                    "enable_written_posts": True,
                    "enable_video_ads": True,
                    "post_frequency": "1 per day"
                },
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        ]
        cls.save_catalog(default_products)

    @classmethod
    def get_product(cls, product_id: str) -> Optional[Dict[str, Any]]:
        """Finds a product by id, slug, or tier code."""
        products = cls.load_catalog()
        for p in products:
            if p.get("id") == product_id or p.get("slug") == product_id or p.get("tier_code") == product_id:
                return p
        return None

    @classmethod
    def add_product(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates and saves a new product."""
        products = cls.load_catalog()
        now_str = datetime.now().isoformat()

        pid = data.get("id")
        if not pid:
            name_clean = re.sub(r"[^a-zA-Z0-9]+", "-", str(data.get("name", "product")).lower()).strip("-")
            pid = f"{name_clean}-{uuid.uuid4().hex[:6]}" if name_clean else f"prod-{uuid.uuid4().hex[:8]}"

        # Check existing
        for p in products:
            if p.get("id") == pid:
                raise ValueError(f"Product with ID '{pid}' already exists.")

        product = {
            "id": pid,
            "name": data.get("name", "Untitled Product"),
            "category": data.get("category", "General"),
            "description": data.get("description", ""),
            "features": data.get("features", []),
            "regular_price": data.get("regular_price", ""),
            "offer_price": data.get("offer_price", ""),
            "currency": data.get("currency", "BDT"),
            "contact_info": {
                "phone": data.get("contact_info", {}).get("phone", ""),
                "whatsapp": data.get("contact_info", {}).get("whatsapp", ""),
                "email": data.get("contact_info", {}).get("email", ""),
                "website": data.get("contact_info", {}).get("website", ""),
                "social_handles": data.get("contact_info", {}).get("social_handles", {})
            },
            "logo_or_image": data.get("logo_or_image", ""),
            "target_audience": data.get("target_audience", "General Customers"),
            "tone_of_voice": data.get("tone_of_voice", "Professional"),
            "auto_campaign_settings": {
                "enable_banners": data.get("auto_campaign_settings", {}).get("enable_banners", True),
                "enable_written_posts": data.get("auto_campaign_settings", {}).get("enable_written_posts", True),
                "enable_video_ads": data.get("auto_campaign_settings", {}).get("enable_video_ads", True),
                "post_frequency": data.get("auto_campaign_settings", {}).get("post_frequency", "1 per day")
            },
            "created_at": now_str,
            "updated_at": now_str
        }

        products.append(product)
        cls.save_catalog(products)
        return product

    @classmethod
    def update_product(cls, product_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates an existing product."""
        products = cls.load_catalog()
        for idx, p in enumerate(products):
            if p.get("id") == product_id:
                # Merge updates
                for k in ["name", "category", "description", "features", "regular_price", "offer_price",
                          "currency", "logo_or_image", "target_audience", "tone_of_voice"]:
                    if k in data:
                        p[k] = data[k]

                if "contact_info" in data:
                    p["contact_info"].update(data["contact_info"])
                if "auto_campaign_settings" in data:
                    p["auto_campaign_settings"].update(data["auto_campaign_settings"])

                p["updated_at"] = datetime.now().isoformat()
                products[idx] = p
                cls.save_catalog(products)
                return p
        return None

    @classmethod
    def delete_product(cls, product_id: str) -> bool:
        """Deletes a product by ID."""
        products = cls.load_catalog()
        initial_count = len(products)
        products = [p for p in products if p.get("id") != product_id]
        if len(products) < initial_count:
            cls.save_catalog(products)
            return True
        return False

    # =========================================================================
    # CONTENT GENERATION ENGINES (Banners, Written Posts, Video Ads)
    # =========================================================================

    @classmethod
    def generate_promotional_banner(cls, product_id: str, style: str = "modern_cyber") -> Path:
        """
        Creates a high-converting branded promotional poster/banner (1080x1350 vertical or 1200x630)
        featuring product name, price badge, offer discount, and contact details.
        """
        product = cls.get_product(product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        width, height = 1080, 1350
        img = Image.new("RGBA", (width, height), (10, 15, 29, 255))
        draw = ImageDraw.Draw(img)

        # Background Gradient & Tech Cyber Grid lines
        for y in range(height):
            ratio = y / height
            r = int(10 + (25 - 10) * ratio)
            g = int(15 + (35 - 15) * ratio)
            b = int(35 + (65 - 35) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # Cyber Grid Lines
        grid_color = (255, 255, 255, 12)
        for x in range(0, width, 60):
            draw.line([(x, 0), (x, height)], fill=grid_color)
        for y in range(0, height, 60):
            draw.line([(0, y), (width, y)], fill=grid_color)

        # Ambient Glow Oval (Center)
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([width//4, height//4, 3*width//4, 3*height//4], fill=(0, 242, 254, 30))
        glow = glow.filter(ImageFilter.GaussianBlur(80))
        img = Image.alpha_composite(img, glow)
        draw = ImageDraw.Draw(img)

        # 1. Top Category Pill Badge
        category_text = f"🔥 {product.get('category', 'SPECIAL OFFER').upper()} • OFFICIAL DEAL"
        f_pill = _get_font(24, bold=True)
        pill_bbox = draw.textbbox((0, 0), category_text, font=f_pill)
        pill_w = pill_bbox[2] - pill_bbox[0] + 40
        pill_h = 44
        pill_x = (width - pill_w) // 2
        pill_y = 60
        draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=22, fill=(2, 132, 199, 230), outline=(56, 189, 248, 255), width=2)
        draw.text((pill_x + 20, pill_y + 8), category_text, fill=(255, 255, 255, 255), font=f_pill)

        # 2. Main Product Title
        name = product.get("name", "Product Name")
        f_title = _get_font(46, bold=True)
        # Word wrap title if long
        words = name.split()
        title_lines = []
        cur_line = ""
        for w in words:
            test_line = f"{cur_line} {w}".strip()
            if len(test_line) > 28:
                if cur_line:
                    title_lines.append(cur_line)
                cur_line = w
            else:
                cur_line = test_line
        if cur_line:
            title_lines.append(cur_line)

        title_y = 140
        for line in title_lines:
            t_bbox = draw.textbbox((0, 0), line, font=f_title)
            t_w = t_bbox[2] - t_bbox[0]
            draw.text(((width - t_w)//2, title_y), line, fill=(255, 255, 255, 255), font=f_title)
            title_y += 58

        # 3. Highlighting Price & Urgency Box
        offer_p = product.get("offer_price", "Special Price")
        reg_p = product.get("regular_price", "")
        box_y = title_y + 20
        box_w = 920
        box_h = 160
        box_x = (width - box_w) // 2
        draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=20, fill=(15, 23, 42, 230), outline=(245, 158, 11, 240), width=3)

        f_deal = _get_font(28, bold=True)
        f_price = _get_font(56, bold=True)
        f_reg = _get_font(28, bold=False)

        draw.text((box_x + 35, box_y + 25), "💥 ধামাকা অফার মূল্য:", fill=(251, 191, 36, 255), font=f_deal)
        draw.text((box_x + 35, box_y + 70), str(offer_p), fill=(16, 185, 129, 255), font=f_price)

        if reg_p:
            reg_text = f"রেগুলার মূল্য: {reg_p}"
            r_bbox = draw.textbbox((0, 0), reg_text, font=f_reg)
            rx = box_x + box_w - (r_bbox[2] - r_bbox[0]) - 35
            draw.text((rx, box_y + 75), reg_text, fill=(244, 63, 94, 255), font=f_reg)
            # Strikethrough line
            draw.line([(rx, box_y + 92), (rx + (r_bbox[2] - r_bbox[0]), box_y + 92)], fill=(244, 63, 94, 255), width=3)

        # 4. Features Checklist Box
        feat_y = box_y + box_h + 35
        feat_w = 920
        feat_h = 420
        feat_x = (width - feat_w) // 2
        draw.rounded_rectangle([feat_x, feat_y, feat_x + feat_w, feat_y + feat_h], radius=20, fill=(20, 27, 45, 210), outline=(59, 130, 246, 120), width=2)

        f_feat_head = _get_font(30, bold=True)
        draw.text((feat_x + 35, feat_y + 25), "⭐ স্পেশাল সুযোগ-সুবিধা ও ফিচারসমূহ:", fill=(56, 189, 248, 255), font=f_feat_head)

        f_feat_item = _get_font(24, bold=False)
        features = product.get("features", [])
        cur_fy = feat_y + 80
        for idx, feat in enumerate(features[:5]):
            feat_line = f"✓  {feat}"
            # truncate if too long
            if len(feat_line) > 55:
                feat_line = feat_line[:52] + "..."
            draw.text((feat_x + 35, cur_fy), feat_line, fill=(226, 232, 240, 255), font=f_feat_item)
            cur_fy += 60

        # 5. Bottom Contact & Action Deck
        contact = product.get("contact_info", {})
        bot_y = height - 260
        bot_w = 920
        bot_h = 210
        bot_x = (width - bot_w) // 2
        draw.rounded_rectangle([bot_x, bot_y, bot_x + bot_w, bot_y + bot_h], radius=24, fill=(16, 185, 129, 240), outline=(52, 211, 153, 255), width=2)

        f_cta_head = _get_font(32, bold=True)
        cta_title = "📞 এখনই অর্ডার করতে যোগাযোগ করুন:"
        cta_bbox = draw.textbbox((0, 0), cta_title, font=f_cta_head)
        draw.text(((width - (cta_bbox[2]-cta_bbox[0]))//2, bot_y + 20), cta_title, fill=(10, 15, 29, 255), font=f_cta_head)

        f_cta_detail = _get_font(26, bold=True)
        c_lines = []
        if contact.get("whatsapp") or contact.get("phone"):
            p_val = contact.get("whatsapp") or contact.get("phone")
            c_lines.append(f"WhatsApp / Call: {p_val}")
        if contact.get("website"):
            c_lines.append(f"Website: {contact.get('website').replace('https://', '')}")
        if contact.get("email"):
            c_lines.append(f"Email: {contact.get('email')}")

        c_y = bot_y + 75
        for cl in c_lines[:3]:
            cl_bbox = draw.textbbox((0, 0), cl, font=f_cta_detail)
            draw.text(((width - (cl_bbox[2]-cl_bbox[0]))//2, c_y), cl, fill=(10, 15, 29, 255), font=f_cta_detail)
            c_y += 40

        # Save image
        out_filename = f"banner_{product_id}_{int(time.time())}.png"
        out_path = BANNERS_DIR / out_filename
        img.convert("RGB").save(str(out_path), "PNG", quality=95)
        print(f"[OmniProductManager] Generated branded banner: {out_path}", flush=True)
        return out_path

    @classmethod
    def generate_written_promotional_post(cls, product_id: str, platform: str = "facebook") -> Dict[str, Any]:
        """
        Creates high-converting promotional post captions & copywriting with dynamic
        hooks, prices, bullet features, and clear contact CTAs.
        """
        product = cls.get_product(product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        name = product.get("name", "")
        category = product.get("category", "")
        desc = product.get("description", "")
        features = product.get("features", [])
        reg_p = product.get("regular_price", "")
        off_p = product.get("offer_price", "")
        contact = product.get("contact_info", {})
        phone = contact.get("whatsapp") or contact.get("phone", "")
        website = contact.get("website", "")
        email = contact.get("email", "")

        feat_str = "\n".join([f"✅ {f}" for f in features])

        # Clean WhatsApp digits for 1-click wa.me URL
        wa_digits = re.sub(r"[^\d]", "", phone)
        wa_link = f"https://wa.me/{wa_digits}" if wa_digits else "https://wa.me/8801968111593"
        web_link = website if (website and website.startswith("http")) else (f"https://{website}" if website else "https://automoviepro.com")

        bonus_text = ""
        scarcity_text = "⚠️ সীমিত সময়ের ২য় স্পেশাল অফার — আগামী ৮-১০ দিন পর রেগুলার মূল্যে ফিরে যাবে!"
        if product_id == "video_studio":
            bonus_text = """🎁 আজকের স্পেশাল ডাবল বোনাস:
✨ ৩য় অতিরিক্ত আন্তর্জাতিক ভাষা (হিন্দি/উর্দু/ইংরেজি - মূল্য ৳৪৯৯) আজীবন ব্যবহারের জন্য সম্পূর্ণ ফ্রি!
✨ ১টি ক্লিকেই ৩টি ফেসবুক পেজ, ৩টি ইউটিউব চ্যানেল ও ৩টি টিকটক একাউন্ট (মোট ৯টি প্ল্যাটফর্মে একসাথে) ভিডিও পোস্ট করে ট্রিপল প্যাসিভ ইনকাম!"""
        elif product_id == "fb_business":
            bonus_text = """🎁 বিজনেসের জন্য বিশেষ সুবিধা:
✨ ৩০-৭০ সেকেন্ডের কাইনেটিক বিজ্ঞাপন ভিডিও মেকার ও প্রোডাক্ট সেলস ব্যানার
✨ টার্গেটেড ফেসবুক গ্রুপে নিরাপদ অর্গানিক পোস্ট শেয়ারিং — জিরো পেইড অ্যাড কস্টে সেলস বৃদ্ধি!"""
        elif product_id == "profile_page":
            bonus_text = """🎁 প্রোফাইল ব্র্যান্ডিংয়ের বিশেষ সুবিধা:
✨ মানুষের স্বাভাবিক মাউস মুভমেন্ট ও অ্যান্টি-ব্যান সেফটি অ্যালগরিদম
✨ প্রতিদিন স্বয়ংক্রিয় অনুপ্রেরণামূলক ও ইসলামিক কোট ব্যানার ও স্ট্যাটাস পাবলিশিং!"""
        elif product_id == "wa_marketing":
            bonus_text = """🎁 ডিরেক্ট সেলস ও মার্কেটিং পাওয়ার:
✨ গুগল ম্যাপস ও বি২বি ডিরেক্টরি থেকে টার্গেটেড লিড স্ক্র্যাপার
✨ ২৪/৭ চ্যাটবট অটো-রিপ্লাই ও আনলিমিটেড বাল্ক মেসেজিং ইঞ্জিন!"""

        post_caption = f"""🚀 【ধামাকা অফার】 {name} নিয়ে এলো সেরা সমাধান!

🌐 ১-ক্লিকে ওয়েবসাইট ভিজিট করুন: {web_link}
💬 ১-ক্লিকে হোয়াটসঅ্যাপে মেসেজ দিন: {wa_link}

{desc}

✨ স্পেশাল ফিচার ও সুবিধাসমূহ:
{feat_str}

💰 রেগুলার মূল্য: {reg_p}
💥 সীমিত সময়ের স্পেশাল অফার মূল্য: মাত্র {off_p}!
{scarcity_text}

{bonus_text}

কেন দেরি করবেন? আপনার প্যাসিভ ইনকাম বা ব্যবসার গ্রোথকে ১০ গুণ সহজ ও প্রফেশনাল করতে আজই সংগ্রহ করুন।

🛒 ১-ক্লিকে অর্ডার ও ইনস্ট্যান্ট এক্সেস:
🌐 ওয়েবসাইট: {web_link}
💬 হোয়াটসঅ্যাপ ডিরেক্ট চ্যাট: {wa_link}
📞 সরাসরি কল / হেল্পলাইন: {phone}
✉️ ইমেইল: {email}

#AutoMoviePro #{category.replace(' ', '')} #SpecialDeal #ExclusiveOffer #PassiveIncome #YouTubeFaceless #Technology #BusinessGrowth #Bangladesh
"""
        return {
            "product_id": product_id,
            "platform": platform,
            "headline": f"🔥 {name} - সীমিত সময়ের বিশেষ অফার {off_p}!",
            "caption": post_caption.strip(),
            "generated_at": datetime.now().isoformat()
        }

    @classmethod
    def create_video_ad_storyboard(
        cls,
        product_id: str,
        ad_type: str = "reel_9_16",
        duration_seconds: int = 45,
        ad_objective: str = "Direct Sale",
        custom_talking_points: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Creates a structured, high-converting video ad storyboard template
        for the given product, compatible with OmniAdStudioGenerator.
        """
        product = cls.get_product(product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        name = product.get("name", "")
        category = product.get("category", "")
        desc = product.get("description", "")
        features = product.get("features", ["১০০% অটোমেশন", "সহজ ইন্টারফেস", "লাইফটাইম ডিল"])
        reg_p = product.get("regular_price", "")
        off_p = product.get("offer_price", "")
        contact = product.get("contact_info", {})
        website = contact.get("website", "automoviepro.com")
        phone = contact.get("whatsapp") or contact.get("phone", "")

        # Dynamic Hook & Talking points
        hook = custom_talking_points.get("hook") if custom_talking_points else f"আপনার {category} নিয়ে কি চিন্তিত? পেয়ে যান সেরা সমাধান!"
        problem = custom_talking_points.get("problem") if custom_talking_points else "প্রতি মাসে অতিরিক্ত খরচ এবং সময় অপচয় বন্ধ করার সময় এসেছে।"
        solution = custom_talking_points.get("solution") if custom_talking_points else f"{name} দিয়ে সম্পূর্ণ কাজ এখন চলবে অটোপাইলটে।"
        offer_cta = custom_talking_points.get("cta") if custom_talking_points else f"রেগুলার {reg_p} এর বদলে এখনই অফারে নিন মাত্র {off_p} টাকায়!"

        # Construct scenes based on duration
        # 15s -> 2 scenes, 30s -> 3 scenes, 45-60s -> 4 scenes, 90s -> 5 scenes
        scenes = [
            {
                "visual_prompt": f"Modern creative workspace technology portrait showcasing {category}, 9:16 vertical portrait",
                "badge_text": f"🔥 {name[:25]}",
                "headline": hook,
                "stat_label": "স্মার্ট সমাধান",
                "stat_val": "১০০% কার্যকারিতা",
                "speech": f"{hook} {problem}"
            },
            {
                "visual_prompt": "Futuristic digital dashboard running smart automated systems smoothly, 9:16 vertical portrait",
                "badge_text": "⚡ অল-ইন-ওয়ান ফিচার",
                "headline": f"{features[0] if features else 'অ্যাডভান্সড ফিচার'}\nখুব সহজেই পরিচালনা করুন!",
                "stat_label": "পাওয়ারফুল ইঞ্জিন",
                "stat_val": "দ্রুত ফলাফল",
                "speech": f"{solution} এর মাধ্যমে {features[0] if features else ''} এবং {features[1] if len(features) > 1 else ''} নিশ্চিত করা সম্ভব।"
            },
            {
                "visual_prompt": "Happy business owner smiling while checking sales growth analytics, 9:16 vertical portrait",
                "badge_text": f"💎 স্পেশাল অফার {off_p}",
                "headline": f"রেগুলার {reg_p} ছাড়িয়ে\nএখনই নিন মাত্র {off_p} টাকায়!",
                "stat_label": "সীমিত অফার",
                "stat_val": "লাইফটাইম ডিল",
                "speech": f"{offer_cta} যোগাযোগ করুন WhatsApp {phone} অথবা ভিজিট করুন {website}।"
            }
        ]

        if duration_seconds >= 45:
            # Add an extra proof / feature scene
            mid_scene = {
                "visual_prompt": "High tech computer monitor showcasing rich content workflow, 9:16 vertical portrait",
                "badge_text": "⭐ নির্ভরযোগ্য পারফরম্যান্স",
                "headline": f"{features[2] if len(features) > 2 else 'প্রিমিয়াম কোয়ালিটি'}\nশত শত গ্রাহকের প্রথম পছন্দ!",
                "stat_label": "কাস্টমার ট্রাস্ট",
                "stat_val": "১০০% স্যাটিসফ্যাকশন",
                "speech": f"আমাদের সিস্টেমে রয়েছে {features[2] if len(features) > 2 else 'প্রিমিয়াম সুযোগ-সুবিধা'} যা আপনাকে দেবে সম্পূর্ণ মানসিক শান্তি।"
            }
            scenes.insert(2, mid_scene)

        ad_id = f"ad_{product_id}_{int(time.time())}"
        template = {
            "id": ad_id,
            "product_id": product_id,
            "theme": f"{name} - {ad_objective}",
            "ad_type": ad_type,
            "duration_seconds": duration_seconds,
            "ad_objective": ad_objective,
            "seed": int(time.time()) % 1000000,
            "avatar_desc": "Professional Bangladeshi presenter in modern high-tech creative studio",
            "voice_gender": "male",
            "scenes": scenes,
            "contact_details": {
                "phone": phone,
                "website": website
            }
        }
        return template

    @classmethod
    def save_ad_to_vault(
        cls,
        product_id: str,
        ad_id: str,
        video_path: str,
        metadata: Dict[str, Any],
        status: str = "draft"
    ) -> Path:
        """
        Saves compiled Ad Video and associated metadata JSON to product_ads_vault.
        """
        ad_folder = VAULT_DIR / ad_id
        ad_folder.mkdir(parents=True, exist_ok=True)

        stored_video_path = video_path
        if video_path and Path(video_path).exists():
            target_video = ad_folder / Path(video_path).name
            if target_video != Path(video_path):
                shutil.copy2(video_path, target_video)
            stored_video_path = str(target_video)

        meta_payload = {
            "ad_id": ad_id,
            "product_id": product_id,
            "status": status,  # draft, approved, scheduled, published
            "video_path": stored_video_path,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata
        }

        meta_file = ad_folder / "ad_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_payload, f, indent=2, ensure_ascii=False)

        print(f"[OmniProductManager] Saved Ad '{ad_id}' to vault: {ad_folder}", flush=True)
        return ad_folder

    @classmethod
    def list_vault_ads(cls, product_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all stored ads in the vault with filter support."""
        ads = []
        if not VAULT_DIR.exists():
            return ads

        for item in VAULT_DIR.iterdir():
            if item.is_dir():
                meta_file = item / "ad_metadata.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if product_id and data.get("product_id") != product_id:
                                continue
                            if status and data.get("status") != status:
                                continue
                            ads.append(data)
                    except Exception:
                        pass
        return sorted(ads, key=lambda x: x.get("created_at", ""), reverse=True)

    @classmethod
    def update_ad_status(cls, ad_id: str, new_status: str, scheduled_time: Optional[str] = None) -> bool:
        """Updates ad status (e.g. draft -> approved -> scheduled -> published)."""
        ad_folder = VAULT_DIR / ad_id
        meta_file = ad_folder / "ad_metadata.json"
        if not meta_file.exists():
            return False

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["status"] = new_status
            data["updated_at"] = datetime.now().isoformat()
            if scheduled_time:
                data["metadata"]["scheduled_time"] = scheduled_time

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[OmniProductManager] Error updating ad status: {e}", flush=True)
            return False


if __name__ == "__main__":
    print("[OmniProductManager] Running self-test...", flush=True)
    products = OmniProductManager.load_catalog()
    print(f"Loaded {len(products)} products from catalog.")
    for p in products:
        print(f" - [{p['id']}] {p['name']} ({p['offer_price']})")
    
    # Generate test banner for first product
    if products:
        first_id = products[0]["id"]
        banner = OmniProductManager.generate_promotional_banner(first_id)
        print(f"Test banner generated at: {banner}")
        copy = OmniProductManager.generate_written_promotional_post(first_id)
        print(f"Test copy headline: {copy['headline']}")
        storyboard = OmniProductManager.create_video_ad_storyboard(first_id, duration_seconds=30)
        print(f"Test storyboard scenes count: {len(storyboard['scenes'])}")
        
        # Test vault save
        OmniProductManager.save_ad_to_vault(
            product_id=first_id,
            ad_id=storyboard["id"],
            video_path="",
            metadata=storyboard,
            status="draft"
        )
        vault_ads = OmniProductManager.list_vault_ads()
        print(f"Total vault ads: {len(vault_ads)}")
    print("OmniProductManager self-test completed successfully.")
