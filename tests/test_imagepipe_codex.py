import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imagepipe.cli import _load_config
from imagepipe.models import CopyTask, ImagePlan, ImageTask
from imagepipe.pipeline import load_run, run
from imagepipe.tool_bridge import accept_image, pending_requests, prepare_tool_args


class CodexImagePipelineTests(unittest.TestCase):
    def test_six_references_keep_original_pixels_and_order_in_three_tool_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references = []
            for index in range(6):
                path = root / f"reference_{index + 1}.png"
                Image.new("RGB", (120 + index, 80 + index), (index * 30, 40, 90)).save(path)
                references.append(path)
            prompt = "Use original reference 6 for the room."
            arguments = prepare_tool_args(prompt, references, root / "sheets")
            self.assertEqual(len(arguments["referenced_image_paths"]), 3)
            self.assertTrue(arguments["prompt"].endswith(prompt))
            self.assertIn("Attached image 3: original reference 5 (left), original reference 6 (right).", arguments["prompt"])
            for index, path in enumerate(arguments["referenced_image_paths"]):
                with Image.open(path) as sheet:
                    left_index, right_index = index * 2, index * 2 + 1
                    self.assertEqual(sheet.size, (240 + left_index + right_index, 144 + right_index))
                    self.assertEqual(sheet.getpixel((0, 64)), (left_index * 30, 40, 90))
                    self.assertEqual(sheet.getpixel((120 + left_index, 64)), (right_index * 30, 40, 90))

    def test_local_tool_exchange_preserves_dependencies_delivery_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = {name: root / f"{name}.png" for name in ("identity", "first", "parallel", "dependent")}
            Image.new("RGB", (48, 80), "teal").save(targets["identity"])
            generated = root / "generated.png"
            Image.new("RGB", (96, 160), "blue").save(generated)
            plan = ImagePlan(str(root), [
                ImageTask("identity", "text", "Existing portrait", [], str(targets["identity"]), 1),
                ImageTask("first", "reference", "First exact system prompt", ["identity"], str(targets["first"]), 2),
                ImageTask("parallel", "reference", "Parallel system prompt", ["identity"], str(targets["parallel"]), 3),
                ImageTask("dependent", "reference", "Dependent system prompt", ["first"], str(targets["dependent"]), 4),
            ], [CopyTask("identity", str(targets["identity"]), str(root / "episode/identity.png"))])
            config = _load_config(Path(__file__).resolve().parents[1] / "configs/imagepipe_codex.yaml", "codex")
            config.api.env_file = str(root / "missing.env")
            config.scheduler.max_active_jobs = 2
            config.scheduler.poll_interval_seconds = 0.01
            run_dir = root / "run"

            async def wait_for_requests(expected):
                deadline = asyncio.get_running_loop().time() + 3
                while asyncio.get_running_loop().time() < deadline:
                    requests = {item["asset_id"]: item for item in pending_requests(run_dir)}
                    if expected <= requests.keys():
                        return requests
                    await asyncio.sleep(0.01)
                raise TimeoutError(f"Missing tool requests: {expected}")

            async def exercise():
                worker = asyncio.create_task(run(plan, config, run_dir))
                requests = await wait_for_requests({"first", "parallel"})
                self.assertNotIn("dependent", requests)
                self.assertEqual(requests["first"]["tool_args"], {
                    "prompt": "First exact system prompt", "transparent_background": False,
                    "referenced_image_paths": [str(targets["identity"])],
                })
                accept_image(run_dir, "first", generated)
                accept_image(run_dir, "parallel", generated)
                requests = await wait_for_requests({"dependent"})
                self.assertEqual(requests["dependent"]["tool_args"]["referenced_image_paths"],
                                 [str(run_dir / "originals/first.png")])
                accept_image(run_dir, "dependent", generated)
                return await asyncio.wait_for(worker, 3)

            with contextlib.redirect_stdout(io.StringIO()):
                report = asyncio.run(exercise())
                targets["dependent"].unlink()
                saved_plan, saved_config = load_run(run_dir)
                resumed = asyncio.run(run(saved_plan, saved_config, run_dir))
            self.assertTrue(report["success"])
            self.assertTrue(resumed["success"])
            self.assertEqual(report["counts"], {"completed": 4})
            self.assertEqual(report["generated"], 3)
            self.assertEqual(report["reused"], 1)
            self.assertEqual(pending_requests(run_dir), [])
            self.assertEqual((root / "episode/identity.png").read_bytes(), targets["identity"].read_bytes())
            for name in ("first", "parallel", "dependent"):
                self.assertEqual(targets[name].read_bytes(), generated.read_bytes())
            records = json.loads((run_dir / "state.json").read_text())["tasks"]
            self.assertEqual(records["dependent"]["attempts"], 1)
            self.assertEqual(records["dependent"]["tool"], "image_gen.imagegen")


if __name__ == "__main__":
    unittest.main()
