"""Privacy-preserving token metering audit helpers.

Ollama's final counters remain authoritative.  The byte-based estimate exists
only to quantify reservation drift and must never be used as a billable value.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
from typing import Iterable, Mapping
from uuid import uuid4


ESTIMATOR_VERSION = "utf8_bytes_div_4_v1"


def parse_token_count(value: object) -> int | None:
    """Return a non-negative provider count, rejecting booleans and coercion."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def estimate_tokens(text: str) -> int:
    """Return a deliberately simple, tokenizer-independent audit estimate."""
    byte_count = len(text.encode("utf-8"))
    return math.ceil(byte_count / 4) if byte_count else 0


def error_metrics(estimated: int, measured: int | None) -> dict[str, int | float | None]:
    if measured is None:
        return {"deltaTokens": None, "errorPercent": None, "absoluteErrorPercent": None}
    delta = estimated - measured
    if measured == 0:
        percentage = 0.0 if estimated == 0 else None
    else:
        percentage = round(delta * 100 / measured, 2)
    return {
        "deltaTokens": delta,
        "errorPercent": percentage,
        "absoluteErrorPercent": abs(percentage) if percentage is not None else None,
    }


def build_audit_record(
    *,
    model: str,
    operation: str,
    prompt_text: str,
    output_text: str,
    prompt_tokens: int | None,
    output_tokens: int | None,
    status: str,
    request_id: str | None = None,
    provider: str = "",
) -> dict[str, object]:
    estimated_prompt = estimate_tokens(prompt_text)
    estimated_output = estimate_tokens(output_text)
    return {
        "version": 1,
        "requestId": request_id or str(uuid4()),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "provider": provider,
        "operation": operation,
        "status": status,
        "estimator": ESTIMATOR_VERSION,
        "promptBytes": len(prompt_text.encode("utf-8")),
        "outputBytes": len(output_text.encode("utf-8")),
        "prompt": {
            "estimatedTokens": estimated_prompt,
            "measuredTokens": prompt_tokens,
            **error_metrics(estimated_prompt, prompt_tokens),
        },
        "output": {
            "estimatedTokens": estimated_output,
            "measuredTokens": output_tokens,
            **error_metrics(estimated_output, output_tokens),
        },
    }


def _aggregate(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    provider_groups: dict[str, dict[str, list[Mapping[str, object]]]] = defaultdict(lambda: defaultdict(list))
    all_records = list(records)
    for record in all_records:
        model = str(record.get("model") or "unknown")
        provider = str(record.get("provider") or "legacy")
        groups[model].append(record)
        provider_groups[provider][model].append(record)

    def summarize(items: list[Mapping[str, object]]) -> dict[str, object]:
        measured = 0
        estimated_total = 0
        measured_total = 0
        absolute_percentages: list[float] = []
        for item in items:
            complete = True
            for field in ("prompt", "output"):
                values = item.get(field)
                if not isinstance(values, Mapping):
                    complete = False
                    continue
                estimated = values.get("estimatedTokens")
                actual = values.get("measuredTokens")
                if isinstance(actual, int) and not isinstance(actual, bool):
                    measured_total += actual
                    if isinstance(estimated, int) and not isinstance(estimated, bool):
                        estimated_total += estimated
                else:
                    complete = False
                absolute_percentage = values.get("absoluteErrorPercent")
                if isinstance(absolute_percentage, (int, float)) and not isinstance(absolute_percentage, bool):
                    absolute_percentages.append(float(absolute_percentage))
            if complete:
                measured += 1
        aggregate_error = error_metrics(estimated_total, measured_total)["errorPercent"] if measured_total else None
        return {
            "requests": len(items),
            "fullyMeasuredRequests": measured,
            "missingMeasurementRequests": len(items) - measured,
            "estimatedTokens": estimated_total,
            "measuredTokens": measured_total,
            "aggregateErrorPercent": aggregate_error,
            "meanAbsoluteFieldErrorPercent": round(sum(absolute_percentages) / len(absolute_percentages), 2)
            if absolute_percentages else None,
        }

    return {
        "estimator": ESTIMATOR_VERSION,
        "overall": summarize(all_records),
        "byModel": {model: summarize(items) for model, items in sorted(groups.items())},
        "byProvider": {
            provider: {"byModel": {model: summarize(items) for model, items in sorted(models.items())}}
            for provider, models in sorted(provider_groups.items())
        },
    }


class JsonlAuditStore:
    """Append-only local audit store that never persists prompt or output text."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: Mapping[str, object]) -> None:
        encoded = json.dumps(dict(record), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

    def read(self, limit: int = 200) -> list[dict[str, object]]:
        if limit < 1 or limit > 1000:
            raise ValueError("Audit limit must be between 1 and 1000")
        with self._lock:
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                return []
        records: list[dict[str, object]] = []
        for line in lines[-limit:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def report(self, limit: int = 200) -> dict[str, object]:
        records = self.read(limit)
        return {"summary": _aggregate(records), "records": records}
