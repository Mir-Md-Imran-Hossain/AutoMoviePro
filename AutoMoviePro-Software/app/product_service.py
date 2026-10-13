"""
=============================================================================
AutoMovie Pro - Product Service & Multi-Product Campaign Engine
=============================================================================
Provides Product Catalog CRUD and promotional asset triggers backed by SQLite
and mirrored with OmniSocial Hub's omni_product_manager.
"""

from __future__ import annotations

import json
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db import db


class ProductService:
    """Manages products and ad campaigns in AutoMovie Pro local database."""

    @classmethod
    def list_products(cls, enabled_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM products"
        params = []
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC"

        with db() as conn:
            rows = conn.execute(query, params).fetchall()
            products = []
            for r in rows:
                p = dict(r)
                p["features"] = json.loads(p.get("features_json") or "[]")
                p["contact_info"] = json.loads(p.get("contact_info_json") or "{}")
                products.append(p)
            return products

    @classmethod
    def get_product(cls, product_id: str) -> Optional[Dict[str, Any]]:
        with db() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                return None
            p = dict(row)
            p["features"] = json.loads(p.get("features_json") or "[]")
            p["contact_info"] = json.loads(p.get("contact_info_json") or "{}")
            return p

    @classmethod
    def create_product(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        pid = data.get("id")
        if not pid:
            name_clean = re.sub(r"[^a-zA-Z0-9]+", "-", str(data.get("name", "product")).lower()).strip("-")
            pid = f"{name_clean}-{uuid.uuid4().hex[:6]}" if name_clean else f"prod-{uuid.uuid4().hex[:8]}"

        now_str = datetime.now().isoformat()
        features_json = json.dumps(data.get("features", []), ensure_ascii=False)
        contact_info_json = json.dumps(data.get("contact_info", {}), ensure_ascii=False)

        with db() as conn:
            conn.execute(
                """
                INSERT INTO products (
                    id, name, category, description, features_json, regular_price,
                    offer_price, contact_info_json, image_path, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    data.get("name", "Untitled Product"),
                    data.get("category", "General"),
                    data.get("description", ""),
                    features_json,
                    data.get("regular_price", ""),
                    data.get("offer_price", ""),
                    contact_info_json,
                    data.get("image_path", ""),
                    1 if data.get("enabled", True) else 0,
                    now_str,
                    now_str
                )
            )

        # Mirror to OmniSocial Hub's catalog if available
        try:
            from omni_product_manager import OmniProductManager
            OmniProductManager.add_product({
                "id": pid,
                "name": data.get("name"),
                "category": data.get("category"),
                "description": data.get("description"),
                "features": data.get("features", []),
                "regular_price": data.get("regular_price"),
                "offer_price": data.get("offer_price"),
                "contact_info": data.get("contact_info", {})
            })
        except Exception:
            pass

        return cls.get_product(pid) or {}

    @classmethod
    def delete_product(cls, product_id: str) -> bool:
        with db() as conn:
            cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            deleted = cur.rowcount > 0

        try:
            from omni_product_manager import OmniProductManager
            OmniProductManager.delete_product(product_id)
        except Exception:
            pass

        return deleted

    @classmethod
    def create_ad_campaign(
        cls,
        product_id: str,
        ad_type: str = "reel_9_16",
        duration_seconds: int = 30,
        talking_points: str = "",
        scheduled_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates an ad record and triggers storyboard / production."""
        ad_id = f"ad_{product_id}_{uuid.uuid4().hex[:6]}"
        now_str = datetime.now().isoformat()

        with db() as conn:
            conn.execute(
                """
                INSERT INTO product_ad_campaigns (
                    id, product_id, ad_type, duration_seconds, talking_points,
                    video_path, status, scheduled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ad_id,
                    product_id,
                    ad_type,
                    duration_seconds,
                    talking_points,
                    "",
                    "draft",
                    scheduled_at,
                    now_str
                )
            )

        # Mirror with OmniProductManager storyboard
        storyboard = None
        banner_path = ""
        try:
            from omni_product_manager import OmniProductManager
            storyboard = OmniProductManager.create_video_ad_storyboard(
                product_id=product_id,
                ad_type=ad_type,
                duration_seconds=duration_seconds
            )
            banner_file = OmniProductManager.generate_promotional_banner(product_id)
            banner_path = str(banner_file)
            OmniProductManager.save_ad_to_vault(
                product_id=product_id,
                ad_id=ad_id,
                video_path="",
                metadata=storyboard,
                status="draft"
            )
        except Exception:
            pass

        return {
            "ad_id": ad_id,
            "product_id": product_id,
            "ad_type": ad_type,
            "duration_seconds": duration_seconds,
            "status": "draft",
            "banner_path": banner_path,
            "storyboard": storyboard,
            "scheduled_at": scheduled_at,
            "created_at": now_str
        }

    @classmethod
    def list_ad_campaigns(cls, product_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM product_ad_campaigns"
        params = []
        if product_id:
            query += " WHERE product_id = ?"
            params.append(product_id)
        query += " ORDER BY created_at DESC"

        with db() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
