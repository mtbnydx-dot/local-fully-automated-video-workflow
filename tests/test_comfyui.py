import json
import os
import subprocess
import sys
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

from videopipe.backends.comfyui import ComfyGenerator, render_workflow
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
            if self.server.mode == "reject":
                self.reply({"error": "prompt_outputs_failed_validation", "node_errors": {"model": "not found"}}, 400)
            else:
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
            if self.server.mode == "error":
                record = {"status": {"status_str": "error", "completed": False, "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]]}, "outputs": {}}
            else:
                outputs = {} if self.server.mode == "no-video" else {"save": {"images": [{"filename": "render.mp4", "subfolder": "videopipe", "type": "output"}]}}
                record = {"status": {"status_str": "success", "completed": True}, "outputs": outputs}
            self.reply({"job-1": record})
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

    def test_generate_uploads_polls_downloads_and_records_real_request(self):
        shot = self.shot(parameters={"steps": 8}, negative_prompt="logos")
        result = ComfyGenerator(self.config).generate(shot, self.output, attempt=2, feedback="Keep the sculpture orange.")
        self.assertEqual(result.read_bytes(), self.video.read_bytes())
        self.assertEqual(self.server.uploads, [("reference.png", self.reference.read_bytes())])
        graph = self.server.submissions[0]["prompt"]
        self.assertEqual(graph["reference"]["inputs"]["image"], "uploaded-reference.png")
        self.assertEqual(graph["conditioning"]["inputs"]["first_frame"], ["first_frame", 0])
        self.assertEqual(graph["first_frame"]["inputs"], {"image": ["reference", 0], "upscale_method": "lanczos",
                                                          "width": shot.width, "height": shot.height, "crop": "center"})
        self.assertEqual(graph["conditioning"]["inputs"]["length"], 124)
        self.assertEqual(graph["noise"]["inputs"]["noise_seed"], shot.seed)
        self.assertEqual(graph["schedule"]["inputs"]["steps"], 8)
        self.assertEqual(graph["conditioning"]["inputs"]["prompt"], shot.prompt)
        self.assertEqual(json.loads((self.output / "workflow.json").read_text()), graph)
        self.assertEqual(json.loads((self.output / "prompt.json").read_text())["prompt_id"], "job-1")
        self.assertEqual(self.server.downloads[0]["subfolder"], ["videopipe"])
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(result), "-f", "null", "-"], check=True)

    def test_text_to_video_selects_graph_without_image_input(self):
        shot = Shot(id="shot-1", prompt="A moving cloud")
        ComfyGenerator(self.config).generate(shot, self.output, attempt=1)
        self.assertEqual(self.server.uploads, [])
        self.assertNotIn("reference", self.server.submissions[0]["prompt"])

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

    def test_review_only_assets_do_not_upload_or_select_i2v(self):
        shot = self.shot(asset_bindings=[
            AssetBinding(asset_id="character", path=self.reference, role="review_only"),
        ])
        ComfyGenerator(self.config).generate(shot, self.output, attempt=1)
        self.assertEqual(self.server.uploads, [])
        self.assertNotIn("reference", self.server.submissions[0]["prompt"])

    def test_legacy_references_upload_only_the_first_frame(self):
        second = Path(self.directory.name) / "review-reference.png"
        Image.new("RGB", (96, 64), "red").save(second)
        shot = Shot(id="legacy", prompt="A slow camera push.", reference_images=[self.reference, second])
        ComfyGenerator(self.config).generate(shot, self.output, attempt=1)
        self.assertEqual(self.server.uploads, [("reference.png", self.reference.read_bytes())])

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

    def test_prompt_whitespace_and_explicit_seed_are_preserved(self):
        text = "  A quiet room.\n\n<d>[Chinese] 原文台词。</d>  \n"
        shot = Shot(id="raw", prompt=text, seed=9345, negative_prompt="new forbidden content")
        ComfyGenerator(self.config).generate(shot, self.output, attempt=3, feedback="Rewrite everything.")
        graph = self.server.submissions[0]["prompt"]
        self.assertEqual(graph["conditioning"]["inputs"]["prompt"], text)
        self.assertEqual(graph["noise"]["inputs"]["noise_seed"], 9345)

    def test_output_prefix_separates_runs_and_upscaled_clips(self):
        root = Path(self.directory.name)
        for run in ("episode-one", "episode-two"):
            ComfyGenerator(self.config).generate(
                self.shot(), root / run / "shots" / "shot-1" / "attempt-001", attempt=1)
        prefixes = [request["prompt"]["save"]["inputs"]["filename_prefix"]
                    for request in self.server.submissions]
        self.assertNotEqual(prefixes[0], prefixes[1])
        self.assertIn("episode-one/shots/shot-1/attempt-001", prefixes[0])
        for shot in ("shot-1", "shot-2"):
            ComfyGenerator(self.config).upscale(
                self.video, root / "episode-one" / "shots" / shot / "attempt-001" / "upscale", factor=2)
        upscaled = [request["prompt"]["save"]["inputs"]["filename_prefix"]
                    for request in self.server.submissions[2:]]
        self.assertNotEqual(upscaled[0], upscaled[1])

    def test_invalid_server_workflow_reports_error_body(self):
        self.server.mode = "reject"
        with self.assertRaisesRegex(RuntimeError, "prompt_outputs_failed_validation"):
            ComfyGenerator(self.config).generate(self.shot(), self.output, attempt=1)
        self.assertTrue((self.output / "submission.json").is_file())

    def test_execution_error_stops_and_retains_history(self):
        self.server.mode = "error"
        with self.assertRaisesRegex(RuntimeError, "CUDA out of memory"):
            ComfyGenerator(self.config).generate(self.shot(), self.output, attempt=1)
        self.assertTrue((self.output / "history.json").is_file())
        self.assertEqual(self.server.downloads, [])

    def test_missing_video_is_not_reported_as_success(self):
        self.server.mode = "no-video"
        with self.assertRaisesRegex(RuntimeError, "without a saved video"):
            ComfyGenerator(self.config).generate(self.shot(), self.output, attempt=1)

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

    def test_upscale_resume_does_not_submit_another_task(self):
        generator = ComfyGenerator(self.config)
        first = generator.upscale(self.video, self.output, factor=2)
        second = generator.upscale(self.video, self.output, factor=2)
        self.assertEqual(first, second)
        self.assertEqual(len(self.server.submissions), 1)
        self.assertEqual(len(self.server.uploads), 1)

    def test_template_keeps_types_and_fails_on_missing_parameter(self):
        self.assertEqual(render_workflow({"size": "{{width}}", "literal": "x={{width}}"}, {"width": 864}), {"size": 864, "literal": "x={{width}}"})
        with self.assertRaisesRegex(ValueError, "Missing workflow parameter: missing"):
            render_workflow({"value": "{{missing}}"}, {})


class ComfyLaunchTests(unittest.TestCase):
    def test_launch_script_passes_mounted_paths_and_offline_options(self):
        script = Path(__file__).resolve().parents[1] / "deploy" / "start-comfyui.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "Comfy UI"
            checkout.mkdir()
            (checkout / "main.py").write_text(
                "import json, os, sys\n"
                "print(json.dumps({'argv': sys.argv, 'gpu': os.environ['CUDA_VISIBLE_DEVICES'], 'offline': os.environ['HF_HUB_OFFLINE']}))\n"
            )
            model_paths = root / "model_paths.yaml"
            model_paths.write_text("local:\n  base_path: /mnt/models\n  diffusion_models: diffusion_models\n")
            env = {**os.environ, "COMFYUI_DIR": str(checkout), "COMFYUI_PYTHON": sys.executable,
                   "COMFY_GPUS": "3", "COMFY_PORT": "8191", "COMFY_MODEL_PATHS": str(model_paths),
                   "COMFY_INPUT_DIR": str(root / "inputs"), "COMFY_OUTPUT_DIR": str(root / "outputs")}
            result = subprocess.run(["bash", str(script), "--cpu"], env=env, capture_output=True, text=True, check=True)
            launch = json.loads(result.stdout)
            self.assertEqual(launch["gpu"], "3")
            self.assertEqual(launch["offline"], "1")
            args = launch["argv"]
            self.assertEqual(args[args.index("--port") + 1], "8191")
            self.assertEqual(args[args.index("--listen") + 1], "127.0.0.1")
            self.assertEqual(args[args.index("--extra-model-paths-config") + 1], str(model_paths))
            self.assertIn("--offline", args)
            self.assertIn("--disable-auto-launch", args)
            self.assertNotIn("--enable-manager", args)
            self.assertEqual(args[-1], "--cpu")
            self.assertTrue((root / "inputs").is_dir())
            self.assertTrue((root / "outputs").is_dir())


if __name__ == "__main__":
    unittest.main()
