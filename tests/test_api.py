from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import server


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary.name)
        self.root = temporary_root / "project"
        self.root.mkdir()
        (self.root / "sample.py").write_text("value = 1\n", encoding="utf-8")
        self.outside = temporary_root / "outside.py"
        self.outside.write_text("secret = True\n", encoding="utf-8")
        (self.root / "escape.py").symlink_to(self.outside)
        self.loop_state_patch = patch.object(server, "LOOP_STATE_PATH", temporary_root / "loop-state.json")
        self.mcp_state_patch = patch.object(server, "MCP_STATE_PATH", temporary_root / "mcp-state.json")
        self.loop_state_patch.start()
        self.mcp_state_patch.start()
        self.application = server.CodeBrowserServer(("127.0.0.1", 0), self.root)
        self.thread = threading.Thread(target=self.application.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.application.shutdown()
        self.application.server_close()
        self.thread.join(timeout=2)
        self.mcp_state_patch.stop()
        self.loop_state_patch.stop()
        self.temporary.cleanup()

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        response_body = json.loads(response.read().decode("utf-8"))
        result = response.status, {key: value for key, value in response.getheaders()}, response_body
        connection.close()
        return result

    def test_security_headers_are_sent(self) -> None:
        status, headers, _ = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_post_requires_code_browser_header(self) -> None:
        status, _, body = self.request("POST", "/api/read-only", {"readOnly": False})
        self.assertEqual(status, 403)
        self.assertIn("Code Browser", body["error"])

        status, _, body = self.request(
            "POST",
            "/api/read-only",
            {"readOnly": False},
            {server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE},
        )
        self.assertEqual(status, 200)
        self.assertFalse(body["readOnly"])

    def test_file_endpoint_rejects_parent_and_symlink_escape(self) -> None:
        for path in ("/api/file?path=../outside.py", "/api/file?path=escape.py"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 403)

    def test_concurrent_mcp_state_updates_leave_valid_json(self) -> None:
        statuses: list[int] = []

        def update(index: int) -> None:
            status, _, _ = self.request(
                "POST",
                "/api/mcp-state",
                {"pinnedProjects": [str(self.root / str(index))], "analyses": [], "current": {}},
                {server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE},
            )
            statuses.append(status)

        workers = [threading.Thread(target=update, args=(index,)) for index in range(12)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)

        self.assertEqual(statuses, [200] * 12)
        state = json.loads(server.MCP_STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 1)
        self.assertEqual(len(state["pinnedProjects"]), 1)


if __name__ == "__main__":
    unittest.main()
