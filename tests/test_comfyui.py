import json
import subprocess
import tempfile
import threading
import unittest
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import imageio_ffmpeg
from PIL import Image

from videopipe.backends.comfyui import ComfyGenerator
from videopipe.models import AssetBinding, ComfyConfig, Shot


class ComfyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {self.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body,
            )
            parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
            part = parts["image"]
            self.server.uploads.append((part.get_filename(), part.get_payload(decode=True)))
            self.server.upload_types.append(part.get_content_type())
            self.reply({"name": "uploaded-" + part.get_filename(), "subfolder": "", "type": "input"})
        elif self.path == "/prompt":
            self.server.submissions.append(json.loads(body))
            self.reply({"prompt_id": "job-1", "node_errors": {}})
        else:
            self.reply({}, 404)

    def do_GET(self):
        route = urlsplit(self.path)
        if route.path == "/history/job-1":
            self.server.polls += 1
            if self.server.polls == 1 or self.server.mode == "timeout":
                self.reply({})
                return
            self.reply({"job-1": {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"save": {"images": [{"filename": "render.mp4", "subfolder": "videopipe", "type": "output"}]}},
            }})
        elif route.path == "/view":
            self.server.downloads.append(parse_qs(route.query))
            data = self.server.video
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.reply({}, 404)


class ComfyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_dir = tempfile.TemporaryDirectory()
        cls.reference = Path(cls.media_dir.name) / "reference.png"
        Image.new("RGB", (96, 64), "orange").save(cls.reference)
        cls.video = Path(cls.media_dir.name) / "source.mp4"
        subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=orange:s=96x64:r=24", "-t", "0.25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.video),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.media_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name) / "attempt-2"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ComfyHandler)
        self.server.mode = "success"
        self.server.video = self.video.read_bytes()
        self.server.uploads = []
        self.server.upload_types = []
        self.server.submissions = []
        self.server.downloads = []
        self.server.polls = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = ComfyConfig(urls=[f"http://127.0.0.1:{self.server.server_port}"], poll_interval=0.01, timeout=2)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.directory.cleanup()

    def shot(self, **kwargs):
        return Shot(id="shot-1", prompt="A slow camera push toward an orange sculpture.", duration=5, reference_images=[self.reference], **kwargs)

    def test_explicit_first_frame_binding_controls_generation(self):
        first = Path(self.directory.name) / "approved-first.png"
        Image.new("RGB", (96, 64), "blue").save(first)
        shot = self.shot(asset_bindings=[
            AssetBinding(asset_id="character", path=self.reference, role="review_only"),
            AssetBinding(asset_id="opening", path=first, role="first_frame"),
        ])
        ComfyGenerator(self.config).generate(shot, self.output, attempt=1)
        self.assertEqual(self.server.uploads, [("approved-first.png", first.read_bytes())])
        graph = self.server.submissions[0]["prompt"]
        self.assertEqual(graph["reference"]["inputs"]["image"], "uploaded-approved-first.png")

    def test_upscale_uploads_video_and_passes_requested_factor(self):
        result = ComfyGenerator(self.config).upscale(self.video, self.output, factor=4)
        self.assertEqual(result.read_bytes(), self.video.read_bytes())
        self.assertEqual(self.server.uploads[0][1], self.video.read_bytes())
        self.assertEqual(self.server.upload_types, ["video/mp4"])
        graph = self.server.submissions[0]["prompt"]
        self.assertEqual(graph["load"]["inputs"]["file"], "uploaded-source.mp4")
        self.assertEqual(graph["width"]["inputs"]["values.b"], 4)
        self.assertEqual(graph["video"]["inputs"]["audio"], ["components", 1])
        self.assertEqual(graph["video"]["inputs"]["fps"], ["components", 2])

    def test_timeout_keeps_prompt_id_without_resubmitting(self):
        self.server.mode = "timeout"
        self.config.timeout = 0.06
        with self.assertRaisesRegex(TimeoutError, "job-1"):
            ComfyGenerator(self.config).generate(self.shot(), self.output, attempt=1)
        self.assertEqual(len(self.server.submissions), 1)
        self.assertTrue((self.output / "prompt.json").is_file())
        self.server.mode = "success"
        self.config.timeout = 2
        # Recovery uses the recorded service URL, even if the caller has another available instance.
        result = ComfyGenerator(self.config, url="http://127.0.0.1:1").generate(
            self.shot(), self.output, attempt=1)
        self.assertEqual(result.read_bytes(), self.video.read_bytes())
        self.assertEqual(len(self.server.submissions), 1)
        self.assertEqual(len(self.server.uploads), 1)


if __name__ == "__main__":
    unittest.main()
