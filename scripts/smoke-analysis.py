#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_REPORT = "Streetlights are out on Rustaveli Avenue near the bus stop."
TERMINAL_STATUSES = {"analyzed", "analysis_failed"}


@dataclass(frozen=True)
class SmokeConfig:
    api_base_url: str
    report_text: str
    language_hint: str | None
    location_hint: str | None
    timeout_seconds: float
    poll_seconds: float


class SmokeError(Exception):
    pass


def main() -> int:
    config = _parse_args()

    try:
        incident = _create_incident(config)
        incident_id = _required_str(incident, "id", "create incident response")
        print(f"created incident: {incident_id}")

        queued = _queue_analysis(config, incident_id)
        job_id = _required_str(queued, "job_id", "queue analysis response")
        queue_name = _required_str(queued, "queue_name", "queue analysis response")
        print(f"queued analysis: job={job_id} queue={queue_name}")

        detail = _poll_incident(config, incident_id)
    except SmokeError as exc:
        print(f"smoke-analysis failed: {exc}", file=sys.stderr)
        return 1

    _print_result(detail)
    return 0 if detail["status"] == "analyzed" else 1


def _parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser(
        description="Create an incident, queue analysis, and poll until analysis completes.",
    )
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="FastAPI base URL. Defaults to API_BASE_URL or http://localhost:8000.",
    )
    parser.add_argument(
        "--report-text",
        default=os.getenv("SMOKE_REPORT", DEFAULT_REPORT),
        help="Incident report text to submit.",
    )
    parser.add_argument(
        "--language-hint",
        default=os.getenv("SMOKE_LANGUAGE_HINT", "en"),
        choices=("ka", "en", ""),
        help="Optional language hint. Use an empty value to omit it.",
    )
    parser.add_argument(
        "--location-hint",
        default=os.getenv("SMOKE_LOCATION_HINT", "Rustaveli Avenue"),
        help="Optional location hint. Use an empty value to omit it.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("SMOKE_TIMEOUT_SECONDS", "180")),
        help="Maximum time to wait for analyzed/analysis_failed status.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.getenv("SMOKE_POLL_SECONDS", "2")),
        help="Polling interval while waiting for analysis.",
    )
    args = parser.parse_args()

    return SmokeConfig(
        api_base_url=args.api_base_url.rstrip("/") + "/",
        report_text=args.report_text,
        language_hint=args.language_hint or None,
        location_hint=args.location_hint or None,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )


def _create_incident(config: SmokeConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {"report_text": config.report_text}
    if config.language_hint:
        payload["language_hint"] = config.language_hint
    if config.location_hint:
        payload["location_hint"] = config.location_hint

    return _request_json(config, "POST", "incidents", payload)


def _queue_analysis(config: SmokeConfig, incident_id: str) -> dict[str, Any]:
    return _request_json(config, "POST", f"incidents/{incident_id}/analyze", None)


def _poll_incident(config: SmokeConfig, incident_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + config.timeout_seconds
    last_status = None

    while time.monotonic() < deadline:
        detail = _request_json(config, "GET", f"incidents/{incident_id}", None)
        status = detail.get("status")
        if status != last_status:
            print(f"status: {status}")
            last_status = status
        if status in TERMINAL_STATUSES:
            return detail
        time.sleep(config.poll_seconds)

    raise SmokeError(
        f"incident {incident_id} did not reach a terminal status within {config.timeout_seconds:.0f}s"
    )


def _request_json(
    config: SmokeConfig,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    url = urljoin(config.api_base_url, path)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SmokeError(f"{method} {url} could not connect: {exc.reason}") from exc

    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"{method} {url} returned non-JSON response: {data[:200]}") from exc
    if not isinstance(parsed, dict):
        raise SmokeError(f"{method} {url} returned JSON that was not an object")
    return parsed


def _print_result(detail: dict[str, Any]) -> None:
    print("analysis result:")
    print(f"  status: {detail.get('status')}")
    print(f"  issue_type: {detail.get('issue_type')}")
    print(f"  severity: {detail.get('severity')}")
    print(f"  confidence: {detail.get('confidence')}")
    print(f"  needs_review: {detail.get('needs_review')}")
    print(f"  failure_details: {detail.get('failure_details')}")


def _required_str(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SmokeError(f"{label} missing string field '{key}'")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
