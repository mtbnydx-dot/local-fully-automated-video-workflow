import asyncio
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scriptpipe.llm import DEFAULT_MODEL, GLMClient


class CompletionHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.requests.append((self.path, self.headers, json.loads(body)))
        packets = [
            {"id": "local-response", "model": "deepseek-v4-1-flash", "choices": [
                {"delta": {"reasoning_content": "private reasoning"}, "finish_reason": None},
            ]},
            {"choices": [{"delta": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
             "usage": {"completion_tokens": 12}},
        ]
        body = "".join(f"data: {json.dumps(packet)}\n\n" for packet in packets)
        body = (body + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ScriptClientTests(unittest.TestCase):
    def test_streaming_request_uses_deepseek_thinking_and_configured_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = ThreadingHTTPServer(("127.0.0.1", 0), CompletionHandler)
            server.requests = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            async def exercise():
                client = GLMClient(
                    "local-test-key", root, f"http://127.0.0.1:{server.server_port}/api/coding/v3",
                    max_tokens=72000,
                )
                try:
                    self.assertEqual(await client.complete("configured", "Write JSON", {"text": "故事"}),
                                     {"ok": True})
                    await client.complete("override", "Write JSON", {}, max_tokens=8192)
                finally:
                    await client.close()

            try:
                asyncio.run(exercise())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

            for path, headers, request in server.requests:
                self.assertEqual(path, "/api/coding/v3/chat/completions")
                self.assertEqual(headers["Authorization"], "Bearer local-test-key")
                self.assertEqual(request["model"], DEFAULT_MODEL)
                self.assertEqual(request["thinking"], {"type": "enabled"})
                self.assertEqual(request["reasoning_effort"], "high")
                self.assertTrue(request["stream"])
            self.assertEqual([request["max_tokens"] for _, _, request in server.requests], [72000, 8192])
            response = json.loads(next(root.glob("configured.*.response.json")).read_text())
            self.assertEqual(response["served_model"], "deepseek-v4-1-flash")
            self.assertEqual(response["reasoning_characters"], len("private reasoning"))
            self.assertEqual(response["usage"]["completion_tokens"], 12)
            self.assertNotIn("private reasoning", json.dumps(response))


if __name__ == "__main__":
    unittest.main()
