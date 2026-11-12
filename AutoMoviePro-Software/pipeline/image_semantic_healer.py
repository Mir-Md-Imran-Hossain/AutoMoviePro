# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Image Semantic Healer (Closed-Loop Visual Forensic Gate)
========================================================================
Audits generated scene images and video keyframes against spoken dialogue,
overall video topic, and pre-render deep visual planning specifications
using Google Gemini Multimodal Vision.

Core Forensic Principles:
1. Deep Semantic Alignment: The visual must profoundly and literally match
   the spoken Bengali dialogue, the video topic, and the pre-planned visual spec.
2. Inviolable 90% Certification Standard:
   Only visuals scoring 90.0% or above receive a clearance certificate ("GRANTED").
   Any score below 90% is rejected ("REJECTED").
3. Closed-Loop Re-Generation & Iterative Re-Audit with Full Forensic History:
   When rejected, Google provides a corrected prompt and stock keywords.
   The scene is regenerated, and the newly generated visual is sent back to Google
   together with all prior forensic audit history until certified or attempts exhausted.
4. Anti-Dummy & Anti-Nitpicking Architecture:
   Authentic Gemini Vision API calls with key rotation, never faking passing scores
   or hallucinating false approvals.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ImageSemanticHealer")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s][ImageHealer][%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
    logger.setLevel(logging.INFO)

from scripts.google_ai_vision_auditor import get_rotated_google_keys
from pipeline.custom_pipeline.media_providers import generate_image_with_fallback


class ImageSemanticHealer:
    """Closed-loop visual semantic forensic auditor and prompt self-healer."""

    QUALITY_BARRIER = 90.0

    @classmethod
    def audit_image_with_vision(
        cls,
        image_path: Path,
        dialogue_bn: str,
        concrete_subject: str,
        topic_bn: str,
        niche: str,
        deep_analysis: Optional[Dict[str, Any]] = None,
        forensic_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Audits an image or video keyframe against:
        1. Bengali Dialogue
        2. Video Topic
        3. Pre-Render Deep Visual Analysis / Expected Specification
        4. Prior Forensic Audit History (for iterative refinement)
        """
        image_path = Path(image_path)
        if not image_path.is_file():
            return {
                "is_relevant": False,
                "accuracy_percentage": 0.0,
                "semantic_score": 0.0,
                "clearance_certificate": "REJECTED",
                "forensic_critique": "Visual file does not exist on disk",
                "details": "Visual file does not exist on disk",
                "corrected_prompt": f"8K photorealistic documentary shot of {concrete_subject or topic_bn}, authentic setting, highly detailed",
                "corrected_stock_keywords": [concrete_subject[:20]] if concrete_subject else ["documentary"]
            }

        # Step 0: Pre-Flight Aesthetic Sharpness & Non-Muddy Contrast Gate
        try:
            from PIL import Image, ImageFilter, ImageStat
            with Image.open(image_path) as _chk_im:
                _gray = _chk_im.convert("L")
                _st = ImageStat.Stat(_gray)
                _m_val, _std_val = _st.mean[0], _st.stddev[0]
                _edges = _gray.filter(ImageFilter.FIND_EDGES)
                _edge_st = ImageStat.Stat(_edges)
                _edge_m = _edge_st.mean[0]

                if _m_val < 25.0 and _std_val < 22.0:
                    logger.warning("❌ [Aesthetic Gate] Rejecting dark/muddy unrecognizable image: %s (mean=%.1f, std=%.1f)", image_path.name, _m_val, _std_val)
                    return {
                        "is_relevant": False,
                        "accuracy_percentage": 25.0,
                        "semantic_score": 25.0,
                        "clearance_certificate": "REJECTED_DARK_BLOB",
                        "forensic_critique": "Visual is an unrecognizable dark muddy blob with zero contrast or distinct features.",
                        "details": "Insufficient lighting and contrast.",
                        "corrected_prompt": f"Volumetric bright cinematic lighting, 8K ultra-detailed sharp documentary shot of {concrete_subject or topic_bn}, vibrant natural colors, razor-sharp textures",
                        "corrected_stock_keywords": [concrete_subject[:20]] if concrete_subject else ["documentary"]
                    }
                if _edge_m < 3.0:
                    logger.warning("❌ [Aesthetic Gate] Rejecting blurry/unfocused image: %s (sharpness=%.2f < 3.0)", image_path.name, _edge_m)
                    return {
                        "is_relevant": False,
                        "accuracy_percentage": 30.0,
                        "semantic_score": 30.0,
                        "clearance_certificate": "REJECTED_BLURRY",
                        "forensic_critique": "Visual is low-resolution, out-of-focus or lacking sharp edge definition.",
                        "details": "Lacks sharp optical focus.",
                        "corrected_prompt": f"8K Hasselblad H6D-100c medium format, razor-sharp optical focus, extreme macro documentary detail of {concrete_subject or topic_bn}, crisp physical textures",
                        "corrected_stock_keywords": [concrete_subject[:20]] if concrete_subject else ["documentary"]
                    }
        except Exception as _e_aes:
            logger.debug("Aesthetic gate note: %s", _e_aes)

        keys = get_rotated_google_keys()
        if not keys:
            logger.warning("No Google API keys available for image healer; rejecting per anti-dummy protocol.")
            return {
                "is_relevant": False,
                "accuracy_percentage": 0.0,
                "semantic_score": 0.0,
                "clearance_certificate": "REJECTED_OFFLINE",
                "forensic_critique": "Google Vision API keys unavailable. Offline verification rejected.",
                "details": "Google Vision API keys unavailable. Offline verification rejected.",
                "corrected_prompt": f"8K photorealistic documentary shot of {concrete_subject or topic_bn}",
                "corrected_stock_keywords": []
            }

        from google import genai
        from google.genai import types

        # 1. Unpack deep dialogue planning specifications & script visual contract
        deep_spec = deep_analysis or {}
        contract = deep_spec.get("script_visual_contract") or {}
        focal_entity = deep_spec.get("focal_entity") or concrete_subject or "Focal subject"
        optical_action = deep_spec.get("optical_action") or "Cinematic motion"
        environment = deep_spec.get("environment") or "Authentic documentary setting"
        expected_spec = deep_spec.get("expected_visual_spec") or f"{focal_entity} depicting {optical_action} in {environment}"
        reasoning_bn = deep_spec.get("visual_reasoning_bn") or ""

        # Pre-Determined Script Visual Blueprint & Camera Angle
        cam_angle = deep_spec.get("camera_angle") or contract.get("camera_angle") or "Cinematic Perspective"
        cam_move = deep_spec.get("camera_movement") or contract.get("camera_movement") or ""
        lighting = deep_spec.get("lighting_setup") or contract.get("lighting_setup") or "Natural Atmospheric Lighting"
        mandatory_elems = deep_spec.get("mandatory_visual_elements") or contract.get("mandatory_visual_elements") or [focal_entity]
        suggested_prompt = deep_spec.get("suggested_visual_prompt") or contract.get("suggested_visual_prompt") or ""

        # 2. Format prior forensic audit history if this is a re-evaluation
        history_block = ""
        if forensic_history:
            h_lines = ["\n📜 পূর্ববর্তী অডিট ব্যর্থতার ফরেনসিক ইতিহাস (PRIOR FAILED AUDIT ATTEMPTS FOR THIS SCENE):"]
            for h in forensic_history:
                h_lines.append(
                    f"- Attempt {h.get('attempt')}: Score {h.get('accuracy_percentage', h.get('semantic_score'))}% | "
                    f"Critique: {h.get('details', '')} | "
                    f"Prompt Tried: '{h.get('tried_prompt', '')[:80]}...'"
                )
            history_block = "\n".join(h_lines) + "\n\n⚠️ RE-EVALUATION DIRECTIVE: You previously rejected this scene. Evaluate if the newly generated visual now successfully resolves the previous defects and satisfies the dialogue and expected visual specification!"

        # 3. Construct forensic prompt
        audit_prompt = f"""You are the Chief Visual Forensic Auditor and Quality Inspector for AutoMovie Pro.
Your mission is to perform an exhaustive, uncompromised semantic audit on the attached visual.
Verify whether the visual exhibits a profound, literal, and thematic match with the spoken Bengali dialogue, the video's topic, and the pre-rendered deep visual planning analysis.

================================================================================
🎯 AUDIT CONTEXT & GROUND-TRUTH PARAMETERS:
================================================================================
1. Spoken Bengali Dialogue: "{dialogue_bn}"
2. Video Topic/Title: "{topic_bn}"
3. Content Niche: "{niche}"
4. Pre-Render Deep Visual Analysis & Expected Specification:
   - Expected Visual Spec: "{expected_spec}"
   - Focal Entity: "{focal_entity}"
   - Optical Action: "{optical_action}"
   - Physical Environment: "{environment}"
   - Semantic Reasoning: "{reasoning_bn}"
5. SCRIPT-ORIGINATED PRE-DETERMINED VISUAL CONTRACT:
   - Required Camera Angle: "{cam_angle}"
   - Camera Movement: "{cam_move}"
   - Target Lighting: "{lighting}"
   - Mandatory Visual Elements: {mandatory_elems}
   - Script Master Prompt Blueprint: "{suggested_prompt}"
{history_block}
================================================================================

STRICT FORENSIC EVALUATION CRITERIA:
1. Deep Semantic & Literal Match to Dialogue & Topic:
   - Does the attached visual clearly and prominently depict the EXACT physical entity ({focal_entity}) and optical action ({optical_action}) required by the spoken dialogue and visual spec?
   - The visual MUST reflect the concrete nouns, textures, materials, and environment specified by the Bengali dialogue and video topic.
   - If the visual displays something generic, off-topic, cartoonish, or unrelated to the dialogue (e.g. mismatched setting, incorrect objects, or abstract clutter), you MUST deduct heavy points.
2. STRICT SCRIPT VISUAL BLUEPRINT & CAMERA ANGLE COMPLIANCE:
   - Camera Angle Fidelity: Does the visual clearly capture the Required Camera Angle ({cam_angle})? If the camera angle slightly differs but the physical subject and environment match the topic and dialogue, DO NOT heavily penalize (max 10 points deduction).
   - Mandatory Elements Check: Are the mandatory physical elements ({mandatory_elems}) clearly visible and recognizable in the frame? If missing or substituted with generic items, DEDUCT 35-50 points.
   - Dialogue-to-Visual Correspondence: Does the visual directly match what the script pre-determined for this exact sentence?
3. The 90% Industrial Certification Barrier:
   - Accuracy Percentage MUST be >= 90.0% to receive a passing clearance certificate ("clearance_certificate": "GRANTED").
   - If accuracy is below 90.0%, you MUST mark "clearance_certificate": "REJECTED" and "is_relevant": false.
3. Actionable Re-Generation Output (Mandatory on Rejection):
   - "forensic_critique": Explain in concise, precise Bengali or English what specific micro-element or subject from the dialogue is missing or inaccurate and why accuracy is below 90%.
   - "corrected_prompt": Write an ultra-detailed, photorealistic 8K cinematic English prompt that focuses 100% on generating the exact missing focal entity and optical action from this dialogue.
   - "corrected_stock_keywords": Provide 2-3 precise English search keywords directly derived from the dialogue's focal nouns for stock footage search.

OUTPUT FORMAT (Strict JSON only):
```json
{{
  "accuracy_percentage": 0.0 to 100.0,
  "clearance_certificate": "GRANTED" or "REJECTED",
  "is_relevant": true or false,
  "forensic_critique": "Explanation of match or defect...",
  "corrected_prompt": "Ultra-detailed 8K prompt if rejected, else empty",
  "corrected_stock_keywords": ["keyword1", "keyword2"]
}}
```"""

        # 4. Execute audit call across rotated keys
        for attempt, key in enumerate(keys):
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=25000))
                img_bytes = image_path.read_bytes()
                mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                img_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)

                vision_models = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
                resp = None
                for v_model in vision_models:
                    try:
                        resp = client.models.generate_content(
                            model=v_model,
                            contents=[img_part, audit_prompt],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.2
                            )
                        )
                        if resp and resp.text:
                            break
                    except Exception as e_vm:
                        if "404" in str(e_vm):
                            continue
                        raise e_vm

                raw_text = (resp.text or "").strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)

                data = json.loads(raw_text)
                accuracy = float(data.get("accuracy_percentage") or data.get("semantic_score") or 0.0)
                cert = str(data.get("clearance_certificate", "")).upper()
                if not cert:
                    cert = "GRANTED" if accuracy >= cls.QUALITY_BARRIER else "REJECTED"

                critique = str(data.get("forensic_critique") or data.get("match_details") or "")
                corr_prompt = str(data.get("corrected_prompt", "")).strip()
                corr_kws = data.get("corrected_stock_keywords", [])
                if not isinstance(corr_kws, list):
                    corr_kws = [str(corr_kws)]

                is_rel = (accuracy >= cls.QUALITY_BARRIER) and (cert == "GRANTED")

                return {
                    "is_relevant": is_rel,
                    "accuracy_percentage": accuracy,
                    "semantic_score": accuracy,
                    "clearance_certificate": cert,
                    "forensic_critique": critique,
                    "details": critique,
                    "corrected_prompt": corr_prompt,
                    "corrected_stock_keywords": corr_kws,
                }
            except Exception as e:
                logger.debug("Image vision audit attempt %d failed: %s", attempt + 1, e)
                continue

        # Zero Dummy Fallback: If network failed, do NOT fake a pass!
        logger.warning("Image vision audit could not connect across keys; returning zero-dummy rejection.")
        return {
            "is_relevant": False,
            "accuracy_percentage": 0.0,
            "semantic_score": 0.0,
            "clearance_certificate": "REJECTED_OFFLINE",
            "forensic_critique": "Vision audit network unreachable across all keys; forcing rigorous re-synthesis",
            "details": "Vision audit network unreachable across all keys; forcing rigorous re-synthesis",
            "corrected_prompt": f"8K cinematic documentary master shot of {focal_entity}, {optical_action} in {environment}, photorealistic 8K, zero people, zero modern artifacts",
            "corrected_stock_keywords": [focal_entity[:20]] if focal_entity else ["documentary"]
        }

    @classmethod
    def heal_scene_image_closed_loop(
        cls,
        image_path: Path,
        dialogue_bn: str,
        concrete_subject: str,
        topic_bn: str,
        niche: str,
        initial_prompt: str = "",
        aspect: str = "16:9",
        deep_analysis: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3,
        allow_stock: bool = True,
        item_index: int = 1,
    ) -> Dict[str, Any]:
        """
        Full Closed-Loop Forensic Workflow:
        1. Deep Forensic Audit against dialogue, topic, and expected visual spec.
        2. Strict 90% Certification Barrier check.
        3. If < 90%: Re-generates visual with Google's corrected prompt / stock keywords.
        4. Re-sends NEW visual + ALL PRIOR FORENSIC DATA to Google Vision until >= 90% or max attempts.
        """
        image_path = Path(image_path)
        logger.info(f"🔍 [Closed-Loop Forensic Scan] Auditing image: {image_path.name} against dialogue: '{dialogue_bn[:40]}...'")

        history: List[Dict[str, Any]] = []
        current_prompt = initial_prompt

        for attempt in range(1, max_attempts + 1):
            audit_res = cls.audit_image_with_vision(
                image_path=image_path,
                dialogue_bn=dialogue_bn,
                concrete_subject=concrete_subject,
                topic_bn=topic_bn,
                niche=niche,
                deep_analysis=deep_analysis,
                forensic_history=history,
            )

            score = float(audit_res.get("accuracy_percentage") or audit_res.get("semantic_score") or 0.0)
            cert = audit_res.get("clearance_certificate", "REJECTED")
            critique = audit_res.get("forensic_critique") or audit_res.get("details", "")

            history.append({
                "attempt": attempt,
                "accuracy_percentage": score,
                "semantic_score": score,
                "clearance_certificate": cert,
                "is_relevant": audit_res.get("is_relevant", False),
                "details": critique,
                "tried_prompt": current_prompt,
            })

            # INVIOLABLE 90% INDUSTRIAL CERTIFICATION GATE
            if score >= cls.QUALITY_BARRIER and cert == "GRANTED":
                logger.info(
                    f"✅ [Google Vision CERTIFIED (Attempt {attempt}/{max_attempts})] "
                    f"Image {image_path.name} | Accuracy: {score:.1f}% >= {cls.QUALITY_BARRIER}% | "
                    f"Clearance Certificate: GRANTED | {critique[:80]}"
                )
                return {
                    "approved": True,
                    "final_score": score,
                    "clearance_certificate": "GRANTED",
                    "attempts": attempt,
                    "history": history,
                    "image_path": str(image_path),
                    "critique": critique,
                }

            # REJECTED: Needs iterative forensic healing
            corrected_prompt = audit_res.get("corrected_prompt", "").strip()
            corrected_kws = audit_res.get("corrected_stock_keywords", [])

            if not corrected_prompt or len(corrected_prompt) < 15:
                focal = deep_analysis.get("focal_entity") if deep_analysis else concrete_subject
                corrected_prompt = (
                    f"8K cinematic documentary master shot of {focal or dialogue_bn}. "
                    f"Atmospheric authentic documentary lighting, master 35mm optical lens cinematography, "
                    f"rich surface textures, zero people, zero modern artifacts, ultra-photorealistic."
                )

            logger.warning(
                f"⚠️ [Google Vision REJECTED (Attempt {attempt}/{max_attempts})] "
                f"Image {image_path.name} | Accuracy: {score:.1f}% < {cls.QUALITY_BARRIER}% | "
                f"Clearance Denied! Reason: {critique[:100]} | "
                f"Regenerating using Vision suggestion: '{corrected_prompt[:80]}...'"
            )

            # Distill critique into memory via PromptEvolutionEngine
            try:
                from pipeline.prompt_evolution_engine import get_prompt_evolution_engine
                pee = get_prompt_evolution_engine()
                pee.learn_from_critique(
                    dialogue=dialogue_bn,
                    original_prompt=current_prompt,
                    google_critique=critique,
                    google_corrected_prompt=corrected_prompt,
                    score=score
                )
            except Exception as _e_learn:
                logger.debug("Prompt evolution learning note: %s", _e_learn)

            # Regenerate using corrected prompt or stock keywords
            current_prompt = corrected_prompt
            try:
                stock_q = " ".join(corrected_kws) if corrected_kws else concrete_subject
                generate_image_with_fallback(
                    prompt=corrected_prompt,
                    out_path=image_path,
                    aspect=aspect,
                    stock_query=stock_q,
                    allow_stock=False,  # Enforce direct AI synthesis with corrected prompt to eliminate stock mismatch
                    item_index=item_index + attempt
                )
                logger.info(f"🔄 Re-synthesized new image for {image_path.name} (Attempt {attempt+1}). Re-auditing with Google Vision...")
            except Exception as e_regen:
                logger.error(f"Image regeneration failed: {e_regen}")
                break

        # Final return after exhausting attempts
        final_rec = history[-1] if history else {}
        final_score = final_rec.get("accuracy_percentage", 0.0)
        final_cert = final_rec.get("clearance_certificate", "REJECTED")
        is_approved = (final_score >= cls.QUALITY_BARRIER) and (final_cert == "GRANTED")

        logger.info(f"🏁 Image forensic audit completed for {image_path.name}: Approved={is_approved} (Score: {final_score:.1f}%)")
        return {
            "approved": is_approved,
            "final_score": final_score,
            "clearance_certificate": final_cert,
            "attempts": len(history),
            "history": history,
            "image_path": str(image_path),
            "critique": final_rec.get("details", "")
        }
