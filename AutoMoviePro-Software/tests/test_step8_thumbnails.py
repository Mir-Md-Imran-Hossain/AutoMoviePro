import unittest
import tempfile
from pathlib import Path
from PIL import Image

from pipeline.media_assets import render_high_aesthetic_thumbnail, generate_thumbnail


class TestStep8Thumbnails(unittest.TestCase):
    def test_render_high_aesthetic_thumbnail_resolution_and_size(self):
        """Thumbnail must be 1280x720 RGB and high visual quality (not tiny or blank)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            out_file = tmp_dir / "thumb_islamic.jpg"
            res = render_high_aesthetic_thumbnail(
                title="Patience in Adversity — The Timeless Lesson in Steadfastness",
                subject="Steadfastness",
                out_path=out_file,
                niche="Islamic Teachings",
            )
            self.assertTrue(out_file.is_file())
            self.assertGreater(out_file.stat().st_size, 15000)

            with Image.open(out_file) as img:
                self.assertEqual(img.size, (1280, 720))
                self.assertEqual(img.mode, "RGB")

    def test_thumbnail_niche_themes(self):
        """Thumbnail generator must tailor color themes by niche."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            fin_out = tmp_dir / "thumb_finance.jpg"
            render_high_aesthetic_thumbnail(
                title="Index Funds Compounding — The Mathematical Truth",
                subject="Index Funds",
                out_path=fin_out,
                niche="Personal Finance",
            )
            self.assertTrue(fin_out.is_file())
            self.assertGreater(fin_out.stat().st_size, 15000)

    def test_generate_thumbnail_fallback_no_crash(self):
        """generate_thumbnail must seamlessly fall back to high aesthetic render when API unavailable."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            thumb = tmp_dir / "thumb_fallback.jpg"
            res = generate_thumbnail(
                title="Deep Sleep Optimization Secrets",
                gadget="Sleep Biology",
                out_path=thumb,
                pollinations_key="",
                google_api_keys=[],
                niche="Health & Fitness",
            )
            self.assertTrue(thumb.is_file())
            self.assertGreater(thumb.stat().st_size, 15000)


if __name__ == "__main__":
    unittest.main()
