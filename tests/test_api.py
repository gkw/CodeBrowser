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
        self.metering_state_patch = patch.object(server, "METERING_AUDIT_PATH", temporary_root / "metering-audit.jsonl")
        self.loop_state_patch.start()
        self.mcp_state_patch.start()
        self.metering_state_patch.start()
        self.application = server.CodeBrowserServer(("127.0.0.1", 0), self.root)
        self.thread = threading.Thread(target=self.application.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.application.shutdown()
        self.application.server_close()
        self.thread.join(timeout=2)
        self.metering_state_patch.stop()
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

    def test_metering_audit_endpoint_reports_validation_summary(self) -> None:
        self.application.metering_audit.append(server.build_audit_record(
            model="test-model",
            operation="summary",
            prompt_text="12345678",
            output_text="1234",
            prompt_tokens=4,
            output_tokens=1,
            status="measured",
            request_id="request-1",
        ))
        status, _, body = self.request("GET", "/api/metering/audit?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(body["summary"]["byModel"]["test-model"]["requests"], 1)
        self.assertEqual(body["records"][0]["requestId"], "request-1")

        status, _, body = self.request("GET", "/api/metering/audit?limit=0")
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "Audit limit must be between 1 and 1000")

    def test_account_credits_reports_byok_without_managed_credentials(self) -> None:
        with patch.dict(server.os.environ, {
            "CODE_BROWSER_MANAGED_WRAPPER_URL": "",
            "CODE_BROWSER_MANAGED_ACCESS_TOKEN": "",
        }):
            status, _, body = self.request("GET", "/api/account/credits")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"available": False, "mode": "byok"})

    def test_managed_credit_balance_returns_only_display_fields(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, *_args):
                return json.dumps({
                    "actorId": "must-not-leak",
                    "plan": "free",
                    "allowancePeriod": "weekly",
                    "periodAllowanceCredits": "100.000",
                    "periodUsedCredits": "12.500",
                    "reservedCredits": "1.000",
                    "remainingCredits": "86.500",
                    "nextGrantAt": "2026-08-17T00:00:00+00:00",
                    "requests": [{"source": "must-not-leak"}],
                }).encode()

        with (
            patch.dict(server.os.environ, {
                "CODE_BROWSER_MANAGED_WRAPPER_URL": "https://credits.example.test",
                "CODE_BROWSER_MANAGED_ACCESS_TOKEN": "server-secret",
            }),
            patch.object(server, "urlopen", return_value=FakeResponse()) as mocked_open,
        ):
            balance = server.fetch_managed_credit_balance()
        self.assertTrue(balance["available"])
        self.assertEqual(balance["remainingCredits"], "86.500")
        self.assertNotIn("actorId", balance)
        self.assertNotIn("requests", balance)
        request = mocked_open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer server-secret")

    def test_pdf_file_endpoint_returns_extracted_read_only_text(self) -> None:
        pdf_path = self.root / "document.pdf"
        pdf_path.write_bytes(b"%PDF-1.6\nfixture")
        extracted = {
            "content": "[Page 1]\nExtracted text",
            "totalPages": 1,
            "extractedPages": 1,
            "truncated": False,
            "engine": "test",
        }
        with patch.object(server, "extract_pdf_text", return_value=extracted):
            status, _, body = self.request("GET", "/api/file?path=document.pdf")
        self.assertEqual(status, 200)
        self.assertEqual(body["content"], extracted["content"])
        self.assertEqual(body["language"], "PDF text")
        self.assertFalse(body["editable"])
        self.assertEqual(body["document"]["totalPages"], 1)

    def test_pdf_viewer_streams_byte_ranges(self) -> None:
        payload = b"%PDF-1.6\n0123456789"
        (self.root / "document.pdf").write_bytes(payload)
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        connection.request("GET", "/api/pdf?path=document.pdf", headers={"Range": "bytes=5-11"})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 206)
        self.assertEqual(response.getheader("Content-Type"), "application/pdf")
        self.assertEqual(response.getheader("Accept-Ranges"), "bytes")
        self.assertEqual(response.getheader("Content-Range"), f"bytes 5-11/{len(payload)}")
        self.assertIn("frame-ancestors 'self'", response.getheader("Content-Security-Policy"))
        self.assertEqual(body, payload[5:12])

    def test_pdf_analysis_uses_document_prompt_instead_of_code_prompt(self) -> None:
        (self.root / "document.pdf").write_bytes(b"%PDF-1.6\nfixture")
        self.application.provider_plugin_id = "ollama-compatible"
        extracted = {
            "content": "[Page 1]\nA mathematical document.",
            "totalPages": 1,
            "extractedPages": 1,
            "truncated": False,
            "engine": "test",
        }
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        payload = json.dumps({
            "path": "document.pdf", "mode": "summary", "model": "third-party-model", "language": "en",
        }).encode()
        with (
            patch.object(server, "extract_pdf_text", return_value=extracted),
            patch.object(server.ProviderPluginClient, "list_models", return_value=["third-party-model"]),
            patch.object(server.ProviderPluginClient, "infer", return_value={"content": "Document summary", "usage": None}) as infer,
        ):
            connection.request("POST", "/api/analyze", body=payload, headers={
                "Content-Type": "application/json",
                server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE,
            })
            response = connection.getresponse()
            response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        prompt = infer.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("<document>", prompt)
        self.assertIn("Points worth understanding", prompt)
        self.assertNotIn("Relationship diagram", prompt)

    def test_selected_provider_plugin_supplies_models_and_analysis(self) -> None:
        self.application.provider_plugin_id = "ollama-compatible"
        with patch.object(server.ProviderPluginClient, "list_models", return_value=["third-party-model"]):
            status, _, body = self.request("GET", "/api/models")
        self.assertEqual(status, 200)
        self.assertEqual(body["host"], "plugin:ollama-compatible")
        self.assertEqual(body["models"], ["third-party-model"])

        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        payload = json.dumps({
            "path": "sample.py", "mode": "summary", "model": "third-party-model", "language": "en",
        }).encode()
        with (
            patch.object(server.ProviderPluginClient, "list_models", return_value=["third-party-model"]),
            patch.object(server.ProviderPluginClient, "infer", return_value={
                "content": "Plugin result", "usage": {"promptTokens": 8, "outputTokens": 3},
            }) as infer,
        ):
            connection.request("POST", "/api/analyze", body=payload, headers={
                "Content-Type": "application/json",
                server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE,
            })
            response = connection.getresponse()
            frames = [json.loads(line) for line in response.read().decode().splitlines()]
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(frames[0]["meta"]["host"], "plugin:ollama-compatible")
        self.assertTrue(frames[0]["meta"]["creditPreview"]["estimated"])
        self.assertGreater(frames[0]["meta"]["creditPreview"]["promptTokens"], 0)
        self.assertIsNotNone(frames[0]["meta"]["creditPreview"]["credits"])
        self.assertEqual(frames[1]["content"], "Plugin result")
        self.assertEqual(frames[1]["usage"]["status"], "plugin_reported")
        file_prompt = infer.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("## Points worth understanding", file_prompt)
        self.assertIn("source_type", file_prompt)
        self.assertIn("file, function, class, ui, data, external, and symbol", file_prompt)
        audit = self.application.metering_audit.report()
        self.assertIn("plugin:ollama-compatible", audit["summary"]["byProvider"])

        project_payload = json.dumps({
            "path": "", "root": str(self.root), "mode": "summary",
            "model": "third-party-model", "language": "ja",
        }).encode()
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        with (
            patch.object(server.ProviderPluginClient, "list_models", return_value=["third-party-model"]),
            patch.object(server.ProviderPluginClient, "infer", return_value={"content": "構成要約", "usage": None}) as project_infer,
        ):
            connection.request("POST", "/api/project-summary", body=project_payload, headers={
                "Content-Type": "application/json",
                server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE,
            })
            project_response = connection.getresponse()
            project_response.read()
        connection.close()
        self.assertEqual(project_response.status, 200)
        project_prompt = project_infer.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("## 理解しておくとよいポイント", project_prompt)
        self.assertIn("元の種類", project_prompt)
        self.assertIn("file、function、class、ui、data、external、symbol", project_prompt)

    def test_pwa_assets_are_served_from_installable_paths(self) -> None:
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        connection.request("GET", "/manifest.webmanifest")
        response = connection.getresponse()
        manifest = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/manifest+json")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(
            {(icon["sizes"], icon["type"]) for icon in manifest["icons"]},
            {("192x192", "image/png"), ("512x512", "image/png")},
        )
        connection.close()

        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        connection.request("GET", "/service-worker.js")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/javascript; charset=utf-8")
        self.assertEqual(response.getheader("Service-Worker-Allowed"), "/")
        self.assertIn("no-store", response.getheader("Cache-Control"))
        self.assertIn("url.pathname.startsWith('/api/')", body)
        connection.close()

        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        connection.request("GET", "/static/app.js")
        response = connection.getresponse()
        app_javascript = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("obsidian-graph", app_javascript)
        self.assertIn("sourceType", app_javascript)
        self.assertIn("Code knowledge graph", app_javascript)
        connection.close()

    def test_explorer_resizer_is_in_app_shell(self) -> None:
        connection = http.client.HTTPConnection(*self.application.server_address, timeout=3)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn('id="explorerResizer"', body)
        self.assertIn('role="separator"', body)

    def test_post_requires_code_browser_header(self) -> None:
        status, _, body = self.request("POST", "/api/read-only", {"readOnly": False})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "This POST request did not originate from the Code Browser interface")

        status, _, body = self.request(
            "POST",
            "/api/read-only",
            {"readOnly": False},
            {server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE},
        )
        self.assertEqual(status, 200)
        self.assertFalse(body["readOnly"])

    def test_root_validation_error_is_english(self) -> None:
        status, _, body = self.request(
            "POST",
            "/api/root",
            {"path": ""},
            {server.POST_REQUEST_HEADER: server.POST_REQUEST_HEADER_VALUE},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "A directory is required")

    def test_file_endpoint_rejects_parent_and_symlink_escape(self) -> None:
        for path in ("/api/file?path=../outside.py", "/api/file?path=escape.py"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path)
                self.assertEqual(status, 403)
                self.assertEqual(body["error"], "Paths outside the browsing root cannot be accessed")

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
