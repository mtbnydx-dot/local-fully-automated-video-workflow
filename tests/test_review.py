import base64
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from videopipe.backends.review import VLLMReviewer
from videopipe.media import run_ffmpeg
from videopipe.models import ReviewConfig, Shot


class ReviewHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.requests.append((
            self.path,
            json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
        ))
        body = json.dumps(self.server.response).encode()
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.reference = cls.root / "reference.png"
        Image.new("RGB", (160, 96), "teal").save(cls.reference)
        cls.video = cls.root / "video.mp4"
        run_ffmpeg([
            "-loop", "1", "-i", str(cls.reference), "-t", "0.5", "-r", "12",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(cls.video),
        ])
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        self.server.requests = []
        self.server.status = 200
        self.set_response({"passed": True, "summary": "Visible requirements met", "issues": []})
        self.shot = Shot(
            id="s1", prompt="A teal landscape", negative_prompt="blur",
            reference_images=[self.reference], acceptance=["Keep the teal palette"],
            duration=0.5, width=160, height=96, fps=12,
        )
        self.config = ReviewConfig(
            backend="vllm", url=f"http://127.0.0.1:{self.server.server_port}/v1",
            sample_frames=2, max_frame_size=128,
        )
        self.reviewer = VLLMReviewer(self.config, script="A quiet landscape sequence.")
        self.output = self.root / self._testMethodName

    def set_response(self, content, finish_reason="stop"):
        self.server.response = {"choices": [{
            "message": {"content": json.dumps(content)}, "finish_reason": finish_reason,
        }]}

    def test_real_http_request_contains_decodable_images_and_structured_schema(self):
        result = self.reviewer.review(
            self.video, shots=[self.shot], scope="shot", output_dir=self.output
        )
        self.assertTrue(result.passed)
        path, payload = self.server.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        parts = payload["messages"][1]["content"]
        texts = "\n".join(part["text"] for part in parts if part["type"] == "text")
        self.assertIn("A quiet landscape sequence", texts)
        self.assertIn("Keep the teal palette", texts)
        images = [part["image_url"]["url"] for part in parts if part["type"] == "image_url"]
        self.assertEqual(len(images), 3)
        for encoded in images:
            prefix, data = encoded.split(",", 1)
            self.assertEqual(prefix, "data:image/jpeg;base64")
            with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                image.load()
                self.assertLessEqual(max(image.size), 128)
        self.assertEqual(json.loads((self.output / "request.json").read_text()), payload)
        self.assertTrue((self.output / "response.txt").is_file())
        self.assertTrue(json.loads((self.output / "result.json").read_text())["passed"])

    def test_evidenced_visual_issue_is_preserved_without_rewriting_authority(self):
        self.set_response({
            "passed": False, "summary": "Subject missing",
            "issues": [{"shot_id": "s1", "category": "generation", "message": "Subject missing in the supplied frame",
                        "timestamps": [0.125]}],
        })
        result = self.reviewer.review(self.video, shots=[self.shot], scope="shot", output_dir=self.output)
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.issues[0].timestamps, [0.125])
        self.assertNotIn("suggested_prompt", result.issues[0].model_dump())

    def test_transcript_comparison_is_text_only_and_advisory(self):
        self.set_response({"matches": False, "summary": "One spoken line is missing", "differences": ["Missing: hello"]})
        expected = [{"shot_id": "s1", "text": "Hello", "shot_start": 0.0, "shot_end": 0.5}]
        result = self.reviewer.compare_transcript(expected, {
            "status": "complete", "segments": [{"start": 0.0, "end": 0.5, "text": "Goodbye",
                                                    "words": [{"start": 0.0, "end": 0.5, "word": "Goodbye"}]}],
        }, self.output)
        self.assertTrue(result["available"])
        self.assertFalse(result["matches"])
        self.assertNotIn("passed", result)
        self.assertEqual(result["differences"], ["Missing: hello"])
        self.assertNotIn("image_url", json.dumps(self.server.requests[0]))
        payload = json.loads(self.server.requests[0][1]["messages"][1]["content"])
        self.assertEqual(payload["expected_dialogue"], expected)
        self.assertNotIn("script", payload)
        self.assertNotIn("words", payload["segments"][0])
        self.assertTrue((self.output / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()
