from pathlib import Path
import tempfile
import unittest

from videopipe.models import Shot
from videopipe.subtitles import create_subtitles


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_original_chinese_and_punctuation_are_kept_with_observed_word_times(self):
        shot = Shot(id="s1", duration=4, prompt="She says <d>[Chinese] 等等，我来了！</d>")
        transcript = {"status": "complete", "segments": [{
            "start": 0.5, "end": 2, "text": "等等我来了", "words": [
                {"start": 0.6, "end": 0.9, "word": "等等", "probability": 0.9},
                {"start": 1.1, "end": 1.8, "word": "我来了", "probability": 0.95},
            ],
        }]}
        result = create_subtitles([shot], transcript, self.root)
        self.assertEqual(result["status"], "complete")
        data = Path(result["path"]).read_text(encoding="utf-8-sig")
        self.assertIn("00:00:00,600 --> 00:00:01,800", data)
        self.assertIn("等等，我来了！", data)
        self.assertNotIn("[Chinese]", data)
        self.assertEqual(shot.prompt, "She says <d>[Chinese] 等等，我来了！</d>")

    def test_missing_dialogue_keeps_script_text_with_explicit_fallback_timing(self):
        shot = Shot(id="s1", duration=4, prompt="<d>[English] Wait.</d> <d>[English] Come back.</d>")
        result = create_subtitles([shot], {"status": "complete", "segments": [
            {"start": 0.5, "end": 1.0, "text": "Wait"},
        ]}, self.root)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["timing"], "mixed")
        self.assertEqual(len(result["fallback"]), 1)
        self.assertIn("Come back", Path(result["path"]).read_text(encoding="utf-8-sig"))
        self.assertEqual(result["fallback"][0]["start"], 1.0)
        self.assertEqual(result["fallback"][0]["end"], 4.0)


if __name__ == "__main__":
    unittest.main()
