import asyncio
import base64
import contextlib
import io
import json
import tempfile
import threading
import unittest
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from imagepipe.models import CopyTask, ImageConfig, ImagePlan, ImageTask
from imagepipe.pipeline import load_run, run


class GPTImageHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        fields, images = {}, []
        if self.headers["Content-Type"].startswith("application/json"):
            fields = json.loads(body)
        else:
            message = BytesParser(policy=default).parsebytes(
                f'Content-Type: {self.headers["Content-Type"]}\r\n\r\n'.encode() + body
            )
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                value = part.get_payload(decode=True)
                if part.get_filename():
                    images.append((name, part.get_filename(), value))
                else:
                    fields[name] = value.decode()
        self.server.requests.append({"path": self.path, "fields": fields, "images": images,
                                     "authorization": self.headers["Authorization"]})
        status = 400 if fields["prompt"] == "reject this request" else 200
        result = {"error": {"message": "Invalid image request"}} if status == 400 else {
            "quality": "max", "data": [{"b64_json": base64.b64encode(self.server.image).decode()}],
            "usage": {"input_tokens": 100, "input_tokens_details": {"text_tokens": 20, "image_tokens": 80},
                      "output_tokens": 200, "total_tokens": 300},
        }
        encoded = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("x-request-id", f"request-{len(self.server.requests)}")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
        pass


class GPTImagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        env = self.root / ".env"
        env.write_text("GPT_IMAGE_TEST_KEY=local-test-key\n")
        image = io.BytesIO()
        Image.new("RGB", (96, 160), "teal").save(image, format="PNG")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), GPTImageHandler)
        self.server.requests = []
        self.server.image = image.getvalue()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = ImageConfig(api={"base_url": f"http://127.0.0.1:{self.server.server_port}",
                                       "env_file": str(env), "key_name": "GPT_IMAGE_TEST_KEY"},
                                  generation={"width": 18, "height": 32})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_generate_edit_references_native_delivery_and_resume(self):
        targets = {name: self.root / "assets" / f"{name}.png" for name in ("identity", "wardrobe", "frame")}
        copied = self.root / "episode" / "identity.png"
        tasks = [
            ImageTask("identity", "text", "A portrait", [], str(targets["identity"]), 1),
            ImageTask("wardrobe", "edit", "Change the outfit", ["identity"], str(targets["wardrobe"]), 2),
            ImageTask("frame", "reference", "One scene", ["identity", "wardrobe"], str(targets["frame"]), 3),
        ]
        plan = ImagePlan(str(self.root), tasks, [CopyTask("identity", str(targets["identity"]), str(copied))])
        run_dir = self.root / "run"
        with contextlib.redirect_stdout(io.StringIO()):
            report = asyncio.run(run(plan, self.config, run_dir))
            saved_plan, saved_config = load_run(run_dir)
            Image.new("RGB", (18, 32), "red").save(targets["identity"])
            targets["wardrobe"].unlink()
            resumed = asyncio.run(run(saved_plan, saved_config, run_dir))
        self.assertTrue(report["success"])
        self.assertTrue(resumed["success"])
        self.assertEqual(report["provider"], "gpt")
        self.assertEqual(report["counts"], {"completed": 3})
        self.assertEqual(len(self.server.requests), 3)
        first, edit, frame = self.server.requests
        self.assertEqual(first["path"], "/v1/images/generations")
        self.assertEqual(first["authorization"], "Bearer local-test-key")
        self.assertEqual(first["fields"], {
            "model": "gpt-image-2.6-sunburst", "prompt": "A portrait", "size": "1152x2048",
            "quality": "max", "complexity": "high", "n": 1, "output_format": "png", "background": "opaque",
        })
        for request, names in [(edit, ["identity.png"]), (frame, ["identity.png", "wardrobe.png"])]:
            self.assertEqual(request["path"], "/v1/images/edits")
            self.assertEqual([image[:2] for image in request["images"]], [("image[]", name) for name in names])
            self.assertTrue(all(image[2] == self.server.image for image in request["images"]))
            self.assertNotIn("seed", request["fields"])
            self.assertNotIn("steps", request["fields"])
        for path in [*targets.values(), copied]:
            self.assertEqual(path.read_bytes(), self.server.image)
            with Image.open(path) as image:
                self.assertEqual((image.size, image.mode), ((96, 160), "RGB"))
        records = json.loads((run_dir / "state.json").read_text())["tasks"]
        self.assertEqual(records["frame"]["request_id"], "request-3")
        self.assertEqual(records["frame"]["usage"]["output_tokens"], 200)
        self.assertEqual(records["wardrobe"]["attempts"], 1)
        self.assertNotIn("job_id", records["frame"])
        self.assertEqual((run_dir / "originals/identity.png").read_bytes(), self.server.image)

    def test_api_error_is_recorded_and_blocks_dependent(self):
        plan = ImagePlan(str(self.root), [
            ImageTask("parent", "text", "reject this request", [], str(self.root / "parent.png"), 1),
            ImageTask("child", "edit", "Edit parent", ["parent"], str(self.root / "child.png"), 2),
        ], [])
        with contextlib.redirect_stdout(io.StringIO()):
            report = asyncio.run(run(plan, self.config, self.root / "run"))
        self.assertFalse(report["success"])
        self.assertEqual(report["counts"], {"failed": 1, "blocked": 1})
        self.assertEqual(len(self.server.requests), 1)
        self.assertIn("HTTP 400", report["errors"]["parent"])


if __name__ == "__main__":
    unittest.main()
