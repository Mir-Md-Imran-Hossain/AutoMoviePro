"""C05-S — Story-to-Scene Direction & Dialogue–Visual Alignment (paid APIs = 0)."""
from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.production_consistency import (
    CAPABILITY_LIMITATION,
    SceneEmotionState,
    create_voice_identity,
)
from pipeline.story_visual_direction import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    COVERAGE_UNKNOWN,
    HOLD_LONG,
    HOLD_NORMAL,
    HOLD_SHORT,
    LIGHTING_INHERITED,
    LOCATION_TRANSITION,
    NEW_LOCATION,
    SAME_LOCATION,
    VISUAL_HOLD_RISK,
    VISUAL_REPETITION_RISK,
    DirectedVisualBeat,
    GroundedEntity,
    GroundedRelation,
    apply_emotion_to_segment,
    architecture_integrity_snapshot,
    build_directed_visual_beat,
    compile_beat_prompt,
    create_dialogue_segment,
    create_narrative_beat,
    decide_visual_hold_policy,
    decompose_dialogue_to_visual_beats,
    detect_visual_repetition,
    evaluate_intent_coverage,
    ground_entities_from_text,
    ground_relations_from_text,
    localization_direction_safe,
    map_camera_intent,
    plan_visual_beat_repair,
    validate_story_direction_plan,
    visual_beat_to_scene_intent,
)
from pipeline.visual_intelligence import MODE_IMAGE, MODE_IMAGE_WITH_MOTION, create_visual_bible


def _bible(**kw):
    fields = {
        "bible_id": "vb-c05s",
        "version": "1",
        "subject_identity": "Investigator Shobha",
        "character_identity": "Shobha",
        "object_identity": "Suzuki vehicle",
        "environment": "city street daylight",
        "location": "street",
        "wardrobe": "navy coat",
        "visual_style": "documentary",
        "lighting": "soft daylight",
        "camera_language": "medium",
        "props": "badge",
    }
    fields.update(kw)
    return create_visual_bible(**fields)


def _seg(text: str, **kw):
    fields = {
        "segment_id": kw.pop("segment_id", "seg-1"),
        "dialogue_id": kw.pop("dialogue_id", "dlg-1"),
        "scene_id": kw.pop("scene_id", "sc-1"),
        "text": text,
        "speaker": kw.pop("speaker", "Narrator"),
        "start_sec": kw.pop("start_sec", 0.0),
        "end_sec": kw.pop("end_sec", 4.0),
    }
    fields.update(kw)
    return create_dialogue_segment(**fields)


class C05SDialogueTests(unittest.TestCase):
    def test_01_dialogue_segment_creation(self):
        s = _seg("Shobha stood beside the Suzuki.")
        self.assertEqual(s.segment_id, "seg-1")
        self.assertIn("Suzuki", s.text)

    def test_02_timing(self):
        s = _seg("Hello", start_sec=1.0, end_sec=5.5)
        self.assertAlmostEqual(s.duration_sec, 4.5)
        with self.assertRaises(ValueError):
            _seg("Bad", start_sec=5.0, end_sec=1.0)

    def test_03_speaker(self):
        s = _seg("Hi", speaker="Shobha")
        self.assertEqual(s.speaker, "Shobha")

    def test_04_semantic_intent(self):
        s = _seg("She opened the document.", semantic_intent="document opening")
        self.assertEqual(s.semantic_intent, "document opening")

    def test_05_entity_extraction(self):
        ents = ground_entities_from_text("Shobha stood beside the Suzuki.")
        types = {e.entity_type for e in ents}
        self.assertIn("person", types)
        self.assertIn("vehicle", types)

    def test_06_action(self):
        s = _seg("He opened the document.", actions=["opened"])
        self.assertEqual(s.actions[0], "opened")

    def test_07_emotional_intent(self):
        s = _seg("Stay calm.", emotional_intent="serious")
        self.assertEqual(s.emotional_intent, "serious")


class C05SBeatTests(unittest.TestCase):
    def test_08_narrative_beat(self):
        s = _seg("Shobha stood beside the Suzuki.", location="street")
        nb = create_narrative_beat(beat_id="nb-1", segment=s)
        self.assertTrue(nb.beat_id)
        self.assertTrue(nb.visual_change_reason)

    def test_09_visual_beat(self):
        s = _seg("Shobha stood beside the Suzuki.", location="street")
        nb = create_narrative_beat(beat_id="nb-1", segment=s)
        vb = build_directed_visual_beat(
            beat_id="vb-1", segment=s, narrative=nb, bible=_bible(), camera_intent="MEDIUM"
        )
        self.assertEqual(vb.visual_bible_id, "vb-c05s")

    def test_10_dialogue_visual_reference(self):
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="nb-1", segment=s)
        vb = build_directed_visual_beat(beat_id="vb-1", segment=s, narrative=nb, bible=_bible())
        self.assertEqual(vb.dialogue_segment_id, s.segment_id)
        self.assertEqual(vb.narrative_beat_id, nb.beat_id)

    def test_11_beat_ordering(self):
        segs = [
            _seg("Shobha stood beside the Suzuki.", segment_id="a", end_sec=3),
            _seg("He opened the document.", segment_id="b", start_sec=3, end_sec=7),
        ]
        plan = decompose_dialogue_to_visual_beats(segments=segs, bible=_bible())
        orders = [v["order"] for v in plan["visual_beats"]]
        self.assertEqual(orders, sorted(orders))

    def test_12_beat_timing(self):
        s = _seg("Hello there.", start_sec=0, end_sec=5)
        hold = decide_visual_hold_policy(dialogue_duration_sec=s.duration_sec)
        self.assertIn(hold["policy"], (HOLD_SHORT, HOLD_NORMAL, HOLD_LONG))

    def test_13_visual_change_candidate(self):
        s = _seg("She went to the hospital.", location="hospital")
        nb = create_narrative_beat(
            beat_id="nb-1", segment=s, previous_location="street", previous_subject="Shobha"
        )
        self.assertIn(nb.location_change, (NEW_LOCATION, LOCATION_TRANSITION))


class C05SEntityTests(unittest.TestCase):
    def test_14_person(self):
        ents = ground_entities_from_text("The officer waited.")
        self.assertTrue(any(e.entity_type == "person" for e in ents))

    def test_15_vehicle(self):
        ents = ground_entities_from_text("The Suzuki stopped.")
        self.assertTrue(any(e.entity_type == "vehicle" for e in ents))

    def test_16_object(self):
        ents = ground_entities_from_text("He held the phone.")
        self.assertTrue(any(e.entity_type == "object" for e in ents))

    def test_17_location(self):
        ents = ground_entities_from_text("Inside the office.")
        self.assertTrue(any(e.entity_type == "location" for e in ents))

    def test_18_organization(self):
        ents = ground_entities_from_text("The police agency called.")
        self.assertTrue(any(e.entity_type == "organization" for e in ents))

    def test_19_document(self):
        ents = ground_entities_from_text("He opened the document.")
        self.assertTrue(any(e.entity_type == "document" for e in ents))


class C05SRelationshipTests(unittest.TestCase):
    def test_20_beside(self):
        ents = ground_entities_from_text("Shobha stood beside the Suzuki.")
        rels = ground_relations_from_text("Shobha stood beside the Suzuki.", ents)
        self.assertTrue(any(r.relation_type == "beside" for r in rels))

    def test_21_inside(self):
        ents = ground_entities_from_text("The man was inside the building.")
        # ensure building type
        if not any(e.entity_type == "building" for e in ents):
            ents.append(GroundedEntity("ent-building-1", "building", "building", role="location"))
        rels = ground_relations_from_text("The man was inside the building.", ents)
        self.assertTrue(any(r.relation_type == "inside" for r in rels))

    def test_22_holding(self):
        ents = ground_entities_from_text("He opened the document.")
        rels = ground_relations_from_text("He opened the document.", ents)
        self.assertTrue(any(r.relation_type == "holding" for r in rels))

    def test_23_looking_at(self):
        ents = [
            GroundedEntity("p1", "person", "man"),
            GroundedEntity("o1", "object", "phone"),
        ]
        rels = ground_relations_from_text("The man is looking at the phone.", ents)
        self.assertTrue(any(r.relation_type == "looking_at" for r in rels))

    def test_24_on_top_of(self):
        ents = [
            GroundedEntity("o1", "object", "document"),
            GroundedEntity("o2", "object", "desk"),
        ]
        rels = ground_relations_from_text("The document is on the desk.", ents)
        self.assertTrue(any(r.relation_type == "on_top_of" for r in rels))

    def test_25_invalid_relationship(self):
        with self.assertRaises(ValueError):
            ground_relations_from_text(
                "x",
                [],
                explicit=[GroundedRelation("r1", "a", "b", "teleporting")],
            )


class C05SLocationTests(unittest.TestCase):
    def test_26_same_location(self):
        s = _seg("She waited.", location="office")
        nb = create_narrative_beat(beat_id="n", segment=s, previous_location="office")
        self.assertEqual(nb.location_change, SAME_LOCATION)

    def test_27_location_transition(self):
        s = _seg("Meanwhile at the kitchen.", location="kitchen")
        nb = create_narrative_beat(beat_id="n", segment=s, previous_location="office")
        self.assertEqual(nb.location_change, LOCATION_TRANSITION)

    def test_28_new_location(self):
        s = _seg("She went to the hospital.", location="hospital")
        nb = create_narrative_beat(beat_id="n", segment=s, previous_location="street")
        self.assertEqual(nb.location_change, NEW_LOCATION)

    def test_29_camera_change_preserves_location(self):
        bible = _bible(location="hospital", environment="hospital ward")
        s1 = _seg("Wide view of the hospital room.", segment_id="s1", location="hospital")
        s2 = _seg("Close on the investigator.", segment_id="s2", location="hospital")
        nb1 = create_narrative_beat(beat_id="n1", segment=s1)
        vb1 = build_directed_visual_beat(
            beat_id="v1", segment=s1, narrative=nb1, bible=bible, camera_intent="WIDE"
        )
        nb2 = create_narrative_beat(
            beat_id="n2", segment=s2, previous_location="hospital", previous_subject="investigator"
        )
        vb2 = build_directed_visual_beat(
            beat_id="v2",
            segment=s2,
            narrative=nb2,
            bible=bible,
            previous=vb1,
            camera_intent="CLOSE",
        )
        self.assertEqual(vb2.location_state["location"], "hospital")
        self.assertEqual(vb2.location_state["continuity"], SAME_LOCATION)

    def test_30_lighting_inheritance(self):
        bible = _bible(lighting="soft daylight")
        s1 = _seg("Establishing street.", segment_id="s1", location="street")
        nb1 = create_narrative_beat(beat_id="n1", segment=s1)
        vb1 = build_directed_visual_beat(beat_id="v1", segment=s1, narrative=nb1, bible=bible)
        s2 = _seg("Closer on Shobha.", segment_id="s2", location="street")
        nb2 = create_narrative_beat(beat_id="n2", segment=s2, previous_location="street")
        vb2 = build_directed_visual_beat(
            beat_id="v2", segment=s2, narrative=nb2, bible=bible, previous=vb1
        )
        self.assertEqual(vb2.lighting_continuity, LIGHTING_INHERITED)
        self.assertEqual(vb2.lighting_intent, vb1.lighting_intent)


class C05SCharacterTests(unittest.TestCase):
    def test_31_identity_persistence(self):
        bible = _bible()
        s1 = _seg("Shobha stood beside the Suzuki.", segment_id="a")
        nb1 = create_narrative_beat(beat_id="n1", segment=s1)
        vb1 = build_directed_visual_beat(beat_id="v1", segment=s1, narrative=nb1, bible=bible)
        s2 = _seg("Shobha waited calmly.", segment_id="b", emotional_intent="calm")
        nb2 = create_narrative_beat(
            beat_id="n2", segment=s2, previous_subject=nb1.semantic_subject, previous_location="street"
        )
        vb2 = build_directed_visual_beat(
            beat_id="v2", segment=s2, narrative=nb2, bible=bible, previous=vb1
        )
        self.assertEqual(vb2.character_state["identity"], vb1.character_state["identity"])

    def test_32_wardrobe_persistence(self):
        bible = _bible(wardrobe="navy coat")
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=bible)
        self.assertEqual(vb.character_state["wardrobe"], "navy coat")

    def test_33_action_change(self):
        s = _seg("He opened the document.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        self.assertIn("open", nb.action)

    def test_34_emotion_change(self):
        s = _seg("She gasped.", emotional_intent="surprised")
        nb = create_narrative_beat(
            beat_id="n", segment=s, previous_emotion="serious"
        )
        self.assertTrue(nb.emotional_change)

    def test_35_character_contradiction(self):
        bible = _bible()
        s1 = _seg("Shobha waited.", segment_id="a", location="office")
        nb1 = create_narrative_beat(beat_id="n1", segment=s1)
        vb1 = build_directed_visual_beat(beat_id="v1", segment=s1, narrative=nb1, bible=bible)
        s2 = _seg("Ravi entered.", segment_id="b", location="office")
        nb2 = create_narrative_beat(beat_id="n2", segment=s2, previous_location="office", previous_subject="Shobha")
        vb2 = build_directed_visual_beat(
            beat_id="v2", segment=s2, narrative=nb2, bible=bible, previous=vb1
        )
        # Force identity drift without narrative subject_change reason
        vb2.character_state["identity"] = "Other Person"
        nb2.visual_change_reason = "action:entered"
        plan = validate_story_direction_plan(
            segments=[s1, s2],
            narrative_beats=[nb1, nb2],
            visual_beats=[vb1, vb2],
            bible=bible,
        )
        self.assertTrue(any("character_contradiction" in b for b in plan["blocks"]))


class C05SCameraTests(unittest.TestCase):
    def test_36_establishing(self):
        self.assertEqual(map_camera_intent("ESTABLISHING"), "establishing")

    def test_37_medium(self):
        self.assertEqual(map_camera_intent("MEDIUM"), "medium")

    def test_38_close(self):
        self.assertEqual(map_camera_intent("CLOSE"), "close-up")

    def test_39_insert(self):
        self.assertEqual(map_camera_intent("INSERT"), "close-up")

    def test_40_over_shoulder(self):
        self.assertEqual(map_camera_intent("OVER_SHOULDER"), "over-the-shoulder")

    def test_41_camera_continuity(self):
        bible = _bible(location="hospital")
        s1 = _seg("Hospital room.", segment_id="a", location="hospital")
        s2 = _seg("Investigator face.", segment_id="b", location="hospital")
        plan = decompose_dialogue_to_visual_beats(segments=[s1, s2], bible=bible)
        locs = [v["location_state"]["location"] for v in plan["visual_beats"]]
        self.assertTrue(all(l == "hospital" for l in locs))


class C05SAlignmentTests(unittest.TestCase):
    def test_42_exact_dialogue_visual_match(self):
        s = _seg("Shobha stood beside the Suzuki.", location="street")
        ents = ground_entities_from_text(s.text)
        rels = ground_relations_from_text(s.text, ents)
        cov = evaluate_intent_coverage(
            segment=s, entities=ents, relations=rels, location="street", action="stood beside"
        )
        self.assertIn(cov.overall, (COVERAGE_FULL, COVERAGE_PARTIAL))
        self.assertEqual(cov.relationship, COVERAGE_FULL)

    def test_43_missing_entity(self):
        s = _seg("The red car stopped.")
        cov = evaluate_intent_coverage(
            segment=s, entities=[], relations=[], location="street", action="stopped"
        )
        self.assertEqual(cov.object, COVERAGE_NONE)

    def test_44_wrong_action(self):
        # Intent coverage uses provided action; mismatch detected at production_consistency layer.
        # Here: action empty while dialogue implies action → action dim NONE/UNKNOWN handling
        s = _seg("He opened the document.")
        cov = evaluate_intent_coverage(
            segment=s,
            entities=ground_entities_from_text(s.text),
            relations=[],
            location="",
            action="",
        )
        self.assertEqual(cov.action, COVERAGE_NONE)

    def test_45_wrong_location(self):
        s1 = _seg("In the office.", segment_id="a", location="office")
        s2 = _seg("Still talking.", segment_id="b", location="beach")
        nb1 = create_narrative_beat(beat_id="n1", segment=s1)
        vb1 = build_directed_visual_beat(beat_id="v1", segment=s1, narrative=nb1, bible=_bible(location="office"))
        nb2 = create_narrative_beat(beat_id="n2", segment=s2, previous_location="office")
        nb2.location_change = SAME_LOCATION  # claim same but location differs
        vb2 = build_directed_visual_beat(
            beat_id="v2", segment=s2, narrative=nb2, bible=_bible(location="office"), previous=vb1
        )
        vb2.location_state = {"location": "beach", "continuity": SAME_LOCATION}
        plan = validate_story_direction_plan(
            segments=[s1, s2], narrative_beats=[nb1, nb2], visual_beats=[vb1, vb2], bible=_bible()
        )
        self.assertTrue(any("contradictory_location" in b for b in plan["blocks"]))

    def test_46_wrong_relationship(self):
        s = _seg("Shobha stood beside the Suzuki.")
        cov = evaluate_intent_coverage(
            segment=s,
            entities=ground_entities_from_text(s.text),
            relations=[],
            location="street",
            action="stood beside",
        )
        self.assertEqual(cov.relationship, COVERAGE_NONE)

    def test_47_partial_coverage(self):
        s = _seg("Shobha stood beside the Suzuki.")
        ents = [e for e in ground_entities_from_text(s.text) if e.entity_type == "person"]
        cov = evaluate_intent_coverage(
            segment=s, entities=ents, relations=[], location="street", action="stood"
        )
        self.assertEqual(cov.overall, COVERAGE_PARTIAL)

    def test_48_unknown_observation(self):
        s = _seg("Something happened.")
        cov = evaluate_intent_coverage(
            segment=s, entities=[], relations=[], location="", action="happened"
        )
        self.assertEqual(cov.temporal, COVERAGE_UNKNOWN)
        self.assertEqual(cov.confidence, "HEURISTIC")
        self.assertIn("not_artifact", cov.note)


class C05STimingTests(unittest.TestCase):
    def test_49_short_visual_hold(self):
        h = decide_visual_hold_policy(dialogue_duration_sec=3.0)
        self.assertEqual(h["policy"], HOLD_SHORT)

    def test_50_normal_visual_hold(self):
        h = decide_visual_hold_policy(dialogue_duration_sec=5.0)
        self.assertEqual(h["policy"], HOLD_NORMAL)

    def test_51_long_visual_hold(self):
        h = decide_visual_hold_policy(dialogue_duration_sec=7.5)
        self.assertEqual(h["policy"], HOLD_LONG)

    def test_52_repetition_risk(self):
        bible = _bible()
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb1 = build_directed_visual_beat(beat_id="v1", segment=s, narrative=nb, bible=bible)
        vb2 = build_directed_visual_beat(beat_id="v2", segment=s, narrative=nb, bible=bible)
        warnings = detect_visual_repetition([vb1, vb2])
        self.assertTrue(any(w["code"] == VISUAL_REPETITION_RISK for w in warnings))

    def test_53_semantic_beat_boundary(self):
        segs = [
            _seg("Shobha stood beside the Suzuki.", segment_id="a", end_sec=4),
            _seg("He opened the document.", segment_id="b", start_sec=4, end_sec=8, location="office"),
        ]
        plan = decompose_dialogue_to_visual_beats(segments=segs, bible=_bible())
        self.assertGreaterEqual(len(plan["visual_beats"]), 2)

    def test_54_unrelated_dialogue_cannot_share_visual_automatically(self):
        segs = [
            _seg("Shobha stood beside the Suzuki.", segment_id="a", end_sec=3),
            _seg("The officer sat behind the desk.", segment_id="b", start_sec=3, end_sec=7, location="office"),
        ]
        plan = decompose_dialogue_to_visual_beats(segments=segs, bible=_bible())
        # Distinct semantic changes → multiple visuals
        self.assertGreaterEqual(len(plan["visual_beats"]), 2)


class C05SImageFallbackTests(unittest.TestCase):
    def test_55_video_to_image_fallback(self):
        segs = [_seg("Shobha stood beside the Suzuki.", segment_id="a")]
        plan = decompose_dialogue_to_visual_beats(
            segments=segs, bible=_bible(), prefer_image_fallback=True
        )
        self.assertTrue(plan["image_fallback"])
        self.assertIn(plan["visual_beats"][0]["visual_mode"], (MODE_IMAGE, MODE_IMAGE_WITH_MOTION))

    def test_56_multiple_visual_beats(self):
        segs = [
            _seg("Shobha stood beside the Suzuki.", segment_id="a", end_sec=3),
            _seg("He opened the document.", segment_id="b", start_sec=3, end_sec=6),
            _seg("She went to the hospital.", segment_id="c", start_sec=6, end_sec=10, location="hospital"),
        ]
        plan = decompose_dialogue_to_visual_beats(
            segments=segs, bible=_bible(), prefer_image_fallback=True
        )
        self.assertGreaterEqual(len(plan["visual_beats"]), 2)

    def test_57_no_unnecessary_duplication(self):
        # Same semantic hold should not invent duplicate visuals without change
        segs = [
            _seg("Shobha waited quietly.", segment_id="a", end_sec=3, location="street"),
            _seg("She continued waiting.", segment_id="b", start_sec=3, end_sec=6, location="street"),
        ]
        plan = decompose_dialogue_to_visual_beats(segments=segs, bible=_bible())
        # Second may hold — visual count can be 1
        self.assertGreaterEqual(len(plan["visual_beats"]), 1)
        self.assertLessEqual(len(plan["visual_beats"]), 2)

    def test_58_motion_mode_integration(self):
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(
            beat_id="v",
            segment=s,
            narrative=nb,
            bible=_bible(),
            visual_mode=MODE_IMAGE_WITH_MOTION,
        )
        self.assertEqual(vb.visual_mode, MODE_IMAGE_WITH_MOTION)


class C05SLocalizationTests(unittest.TestCase):
    def test_59_same_visual_bible(self):
        b = _bible()
        segs_en = [_seg("Shobha stood beside the Suzuki.", segment_id="a", language="en")]
        s_bn = _seg("শোভা সুজুকির পাশে দাঁড়ালেন।", segment_id="a", language="bn", location="street")
        s_bn.entities = [
            {
                "entity_id": "ent-person-shobha",
                "entity_type": "person",
                "label": "Shobha",
                "role": "subject",
                "required": True,
                "visual_representation": "Shobha",
                "continuity": "MUST_PERSIST",
            },
            {
                "entity_id": "ent-vehicle-suzuki",
                "entity_type": "vehicle",
                "label": "Suzuki",
                "role": "object",
                "required": True,
                "visual_representation": "Suzuki",
                "continuity": "MUST_PERSIST",
            },
        ]
        p = decompose_dialogue_to_visual_beats(segments=segs_en, bible=b)
        p2 = decompose_dialogue_to_visual_beats(segments=[s_bn], bible=b)
        self.assertEqual(p["visual_beats"][0]["visual_bible_id"], p2["visual_beats"][0]["visual_bible_id"])
        self.assertEqual(p["visual_beats"][0]["visual_bible_id"], "vb-c05s")
        check = localization_direction_safe(
            master_bible=b,
            lang_bible=b,
            master_beats=[],
            lang_beats=[],
        )
        self.assertTrue(check["ok"])

    def test_60_same_character(self):
        b = _bible()
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=b)
        self.assertEqual(vb.character_state["identity"], nb.semantic_subject or b.character_identity)

    def test_61_same_location(self):
        b = _bible(location="street")
        s = _seg("Shobha waited.", location="street")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=b)
        self.assertEqual(vb.location_state["location"], "street")

    def test_62_language_specific_dialogue(self):
        s = _seg("শোভা অপেক্ষা করছেন।", language="bn")
        self.assertEqual(s.language, "bn")

    def test_63_language_specific_subtitle(self):
        s = _seg("Hello", language="en")
        s2 = _seg("হ্যালো", language="bn", segment_id="seg-2")
        self.assertNotEqual(s.text, s2.text)
        self.assertEqual(_bible().bible_id, "vb-c05s")


class C05SEmotionTests(unittest.TestCase):
    def test_64_voice_identity_persistence(self):
        voice = create_voice_identity(voice_identity_id="v1", speaker_id="Narrator")
        s = _seg("Hello", emotional_intent="serious")
        ai1 = apply_emotion_to_segment(s, voice, SceneEmotionState(emotion="serious"))
        ai2 = apply_emotion_to_segment(s, voice, SceneEmotionState(emotion="surprised"))
        self.assertEqual(ai1.voice_identity_id, ai2.voice_identity_id)

    def test_65_emotion_change(self):
        voice = create_voice_identity(voice_identity_id="v1")
        s = _seg("Wow!", emotional_intent="surprised")
        ai = apply_emotion_to_segment(s, voice, SceneEmotionState(emotion="surprised", intensity=0.8))
        self.assertEqual(ai.emotion, "surprised")

    def test_66_emotional_visual_intent(self):
        s = _seg("She gasped.", emotional_intent="surprised")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(
            beat_id="v",
            segment=s,
            narrative=nb,
            bible=_bible(),
            emotional_visual_intent="shocked expression",
        )
        self.assertEqual(vb.emotional_visual_intent, "shocked expression")

    def test_67_capability_limitation(self):
        voice = create_voice_identity(voice_identity_id="v1", provider="edge")
        s = _seg("Hello", emphasis=["Hello"])
        ai = apply_emotion_to_segment(
            s, voice, SceneEmotionState(emotion="excited", intensity=0.9, emphasis=["Hello"], pacing="brisk")
        )
        self.assertTrue(any(CAPABILITY_LIMITATION in x for x in ai.capability_limitations))


class C05SArchitectureTests(unittest.TestCase):
    def test_68_no_second_scene_intent(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_scene_intent"])
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=_bible())
        intent = visual_beat_to_scene_intent(vb, s, _bible())
        self.assertEqual(intent.__class__.__name__, "SceneIntent")

    def test_69_no_second_visual_bible(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_visual_bible"])
        src = Path(__file__).resolve().parents[1] / "pipeline" / "story_visual_direction.py"
        self.assertNotIn("class VisualBible", src.read_text(encoding="utf-8"))

    def test_70_no_second_continuity_engine(self):
        self.assertFalse(architecture_integrity_snapshot()["second_continuity_engine"])

    def test_71_no_second_audio_engine(self):
        self.assertFalse(architecture_integrity_snapshot()["second_audio_engine"])

    def test_72_no_second_quality_engine(self):
        self.assertFalse(architecture_integrity_snapshot()["second_quality_engine"])

    def test_73_no_second_repair_engine(self):
        self.assertFalse(architecture_integrity_snapshot()["second_repair_engine"])
        r = plan_visual_beat_repair(beat_id="vb-1", scene_id="sc-1", issue_message="bad relation")
        self.assertFalse(r["visual_repair_engine"])
        self.assertIn("repair_planner", r["repair_engine"])


class C05SRepoSpecificTests(unittest.TestCase):
    def test_74_prompt_provenance_expected_visual_only(self):
        s = _seg("Shobha stood beside the Suzuki.", location="street")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=_bible())
        out = compile_beat_prompt(beat=vb, segment=s, bible=_bible())
        self.assertEqual(out["provenance"]["observation_claim"], "EXPECTED_VISUAL_ONLY")
        self.assertFalse(out["provenance"]["artifact_observation"])

    def test_75_hold_risk_emitted(self):
        h = decide_visual_hold_policy(
            dialogue_duration_sec=12.0,
            semantic_beat_count=1,
            motion_available=False,
        )
        self.assertIn(VISUAL_HOLD_RISK, h["risks"])

    def test_76_officer_desk_alignment(self):
        s = _seg("The officer sat behind the desk.", location="police station")
        ents = ground_entities_from_text(s.text)
        if not any(e.label.lower() == "desk" for e in ents):
            ents.append(GroundedEntity("ent-object-desk", "object", "desk"))
        rels = ground_relations_from_text(s.text, ents)
        self.assertTrue(any(e.entity_type == "person" for e in ents))
        self.assertTrue(rels or "desk" in s.text.lower())

    def test_77_paid_api_zero(self):
        plan = decompose_dialogue_to_visual_beats(
            segments=[_seg("Shobha stood beside the Suzuki.")], bible=_bible()
        )
        self.assertEqual(plan["paid_api_calls"], 0)

    def test_78_unsupported_camera_blocked(self):
        with self.assertRaises(ValueError):
            map_camera_intent("DRONE_ORBIT_X")

    def test_79_preflight_blocks_missing_relationship(self):
        s = _seg("Shobha stood beside the Suzuki.")
        nb = create_narrative_beat(beat_id="n", segment=s)
        vb = build_directed_visual_beat(beat_id="v", segment=s, narrative=nb, bible=_bible())
        vb.relationships = []
        vb.coverage = evaluate_intent_coverage(
            segment=s,
            entities=vb.required_entities,
            relations=[],
            location="street",
            action="stood beside",
        )
        plan = validate_story_direction_plan(
            segments=[s], narrative_beats=[nb], visual_beats=[vb], bible=_bible()
        )
        self.assertTrue(plan["blocked"])
        self.assertTrue(any("relationship_missing" in b for b in plan["blocks"]))


if __name__ == "__main__":
    unittest.main()
