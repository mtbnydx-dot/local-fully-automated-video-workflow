from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from videopipe.backends.asr import _transcribe_local


class ASRTests(unittest.TestCase):
    def test_worker_uses_local_single_input_and_observed_words(self):
        word = SimpleNamespace(start=0.2, end=0.8, word="Hello", probability=0.9)
        segment = SimpleNamespace(start=0.1, end=1.0, text="Hello", words=[word])
        info = SimpleNamespace(language="en", language_probability=0.99)
        calls = {}

        class Model:
            def __init__(self, name, **kwargs):
                calls["init"] = kwargs

            def transcribe(self, path, **kwargs):
                calls["transcribe"] = kwargs
                return iter([segment]), info

        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=Model)}):
            result = _transcribe_local(Path("clip.mp4"), "/local/model", "int8_float16", "en")
        self.assertTrue(calls["init"]["local_files_only"])
        self.assertEqual(calls["init"]["device_index"], 0)
        self.assertEqual(calls["init"]["num_workers"], 1)
        self.assertEqual(calls["transcribe"]["beam_size"], 1)
        self.assertTrue(calls["transcribe"]["word_timestamps"])
        self.assertEqual(result["segments"][0]["words"][0]["start"], 0.2)


if __name__ == "__main__":
    unittest.main()
