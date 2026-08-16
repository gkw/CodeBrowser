from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from metering import JsonlAuditStore, build_audit_record, calculate_credits, estimate_tokens, parse_token_count


class MeteringTests(unittest.TestCase):
    def test_provider_counts_require_non_negative_integers(self) -> None:
        self.assertEqual(parse_token_count(0), 0)
        self.assertEqual(parse_token_count(42), 42)
        for invalid in (-1, True, 1.5, "42", None):
            with self.subTest(invalid=invalid):
                self.assertIsNone(parse_token_count(invalid))

    def test_credits_expose_input_output_and_model_weight_breakdown(self) -> None:
        environment = {
            "CODE_BROWSER_CREDIT_CATALOG_VERSION": "test-v2",
            "CODE_BROWSER_CREDIT_INPUT_PER_1K": "1",
            "CODE_BROWSER_CREDIT_OUTPUT_PER_1K": "2",
            "CODE_BROWSER_CREDIT_MODEL_WEIGHTS": '{"large-model": 3}',
        }
        with patch.dict("os.environ", environment, clear=False):
            credits = calculate_credits("large-model", 1000, 500)
        self.assertEqual(credits["catalogVersion"], "test-v2")
        self.assertEqual(credits["inputCredits"], 3.0)
        self.assertEqual(credits["outputCredits"], 3.0)
        self.assertEqual(credits["totalCredits"], 6.0)
        self.assertEqual(credits["modelWeight"], 3.0)

    def test_audit_record_contains_no_source_or_response_text(self) -> None:
        record = build_audit_record(
            model="example-model",
            operation="summary",
            prompt_text="private source code",
            output_text="private response",
            prompt_tokens=8,
            output_tokens=5,
            status="measured",
            request_id="request-1",
            provider="plugin:example",
        )
        serialized = json.dumps(record)
        self.assertNotIn("private source code", serialized)
        self.assertNotIn("private response", serialized)
        self.assertEqual(record["promptBytes"], 19)
        self.assertEqual(record["prompt"]["estimatedTokens"], estimate_tokens("private source code"))
        self.assertEqual(record["prompt"]["measuredTokens"], 8)
        self.assertEqual(record["provider"], "plugin:example")

    def test_report_exposes_model_error_and_missing_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlAuditStore(Path(directory) / "audit.jsonl")
            store.append(build_audit_record(
                model="model-a", operation="summary", prompt_text="12345678", output_text="1234",
                prompt_tokens=4, output_tokens=1, status="measured", request_id="one",
            ))
            store.append(build_audit_record(
                model="model-a", operation="review", prompt_text="1234", output_text="",
                prompt_tokens=None, output_tokens=None, status="missing", request_id="two",
            ))
            report = store.report()

        summary = report["summary"]["byModel"]["model-a"]
        self.assertEqual(summary["requests"], 2)
        self.assertEqual(summary["fullyMeasuredRequests"], 1)
        self.assertEqual(summary["missingMeasurementRequests"], 1)
        self.assertEqual(summary["estimatedTokens"], 3)
        self.assertEqual(summary["measuredTokens"], 5)
        self.assertEqual(summary["aggregateErrorPercent"], -40.0)
        self.assertIn("legacy", report["summary"]["byProvider"])
        self.assertEqual(len(report["records"]), 2)

    def test_read_skips_truncated_jsonl_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text('{"requestId":"ok"}\n{"requestId":', encoding="utf-8")
            records = JsonlAuditStore(path).read()
        self.assertEqual(records, [{"requestId": "ok"}])

    def test_report_preserves_the_credit_catalog_used_by_each_request(self) -> None:
        with patch.dict("os.environ", {
            "CODE_BROWSER_CREDIT_INPUT_PER_1K": "1",
            "CODE_BROWSER_CREDIT_OUTPUT_PER_1K": "1",
            "CODE_BROWSER_CREDIT_MODEL_WEIGHTS": "{}",
        }, clear=False):
            record = build_audit_record(
                model="model-a", operation="summary", prompt_text="x", output_text="y",
                prompt_tokens=1000, output_tokens=500, status="measured",
            )
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlAuditStore(Path(directory) / "audit.jsonl")
            store.append(record)
            with patch.dict("os.environ", {"CODE_BROWSER_CREDIT_INPUT_PER_1K": "99"}, clear=False):
                report = store.report()
        self.assertEqual(report["summary"]["overall"]["credits"]["totalCredits"], 1.5)


if __name__ == "__main__":
    unittest.main()
