"""Bounded, journaled collection jobs, not independent autonomous agents.

Historical parallel aliases now submit sequential, at-most-three-question
research collection to the shared job service. No convergence/factual verification
claim, synthetic telemetry, implicit notification, auto retry or booking.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from ultron.actions.web_search import research as collect_research
from ultron.core.background_jobs import get_service
from ultron.core.web_research import ResearchReport, format_report
from ultron.paths import PROJECT_ROOT

_REPORTS_DIR = PROJECT_ROOT / "memory" / "drone_reports"


def _text(value, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError("Provide non-empty bounded text")
    return value.strip()


def _save(ctx, body):
    ctx.checkpoint()
    truncated = len(body) > 48000
    if truncated:
        body = body[:48000] + "\nPARTIAL: report character cap reached; content omitted.\n"
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _REPORTS_DIR / f"job_{ctx.job_id}.md"
    ctx.begin_effect()
    # Exact job ID, no target/ticker path interpolation and no overwrite.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        directory = os.open(_REPORTS_DIR, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return {"report_name": path.name, "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "truncated": truncated, "verified": False,
            "note": "Local unverified collection only. No Telegram notification sent."}


def _research_job(ctx, missions):
    sections, successful, partial = [], 0, False
    for index, mission in enumerate(missions, 1):
        ctx.call()
        try:
            report = collect_research(mission, "research", 5)
            if not isinstance(report, ResearchReport):
                raise ValueError("Invalid research result")
            text = format_report(report)
            successful += int(bool(report.results))
            partial |= bool(report.issues) or not report.results
        except Exception:
            partial = True
            text = "Research collection failed; no source evidence obtained for this subquestion."
        # A late provider response cannot publish after cancellation/deadline.
        ctx.checkpoint()
        sections.append(f"## Subquestion {index}\n{text}\n")
    if not successful:
        return {"state": "failed", "note": "No usable sources returned. No report or factual verification certified."}
    result = _save(ctx, "# Bounded research collection\n\n"
                   "Sequential evidence retrieval, not autonomous multi-agent reasoning. "
                   "No independent fact-check, consensus or convergence measurement.\n\n" + "\n".join(sections))
    return {"state": "partial" if partial or result["truncated"] else "completed", **result}


def _market_price(ticker):
    import requests
    ids = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin"}
    with requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids[ticker], "vs_currencies": "usd"},
                      stream=True, timeout=(3, 7), allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("Market source refused")
        raw = bytearray()
        for chunk in response.iter_content(1024):
            raw.extend(chunk)
            if len(raw) > 4096:
                raise ValueError("Market response too large")
    value = json.loads(raw)[ids[ticker]]["usd"]
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("No valid quote")
    return value


def _sample_job(ctx, kind, target, interval, iterations):
    rows, missing = [], 0
    for index in range(iterations):
        ctx.call()
        try:
            if kind == "market":
                value = {"ticker": target, "usd": _market_price(target)}
            else:
                import psutil
                value = {"cpu_percent": psutil.cpu_percent(interval=None), "ram_percent": psutil.virtual_memory().percent}
            # A sample is not a real-time/live quote or a future price guarantee.
            text = json.dumps({"observed_at_utc": datetime.now(timezone.utc).isoformat(), **value})
        except Exception:
            missing += 1
            text = "Sample unavailable; no synthetic zero substituted."
        ctx.checkpoint()
        rows.append(f"- Sample {index + 1}: {text}")
        if index + 1 < iterations:
            ctx.wait(interval)
    if missing == iterations:
        return {"state": "failed", "note": "All samples unavailable. No telemetry result certified."}
    result = _save(ctx, f"# Bounded {kind} samples\n\nPartial/missing readings are explicit. "
                   "CPU first-sample accuracy and market freshness depend on the provider. "
                   "Market source: https://www.coingecko.com/ ; USD observations, not financial advice.\n\n" + "\n".join(rows))
    return {"state": "partial" if missing else "completed", **result}


def launch_drone(drone_type: str, target: str, interval: int = 30, iterations: int = 1) -> str:
    if type(interval) is not int or not 5 <= interval <= 60 or type(iterations) is not int or not 1 <= iterations <= 10:
        raise ValueError("Finite budgets required")
    if drone_type in {"research", "recon", "intel"}:
        return swarm_parallel_execute(target)
    aliases = {"market": "market", "crypto": "market", "price": "market", "system": "system", "sentry": "system", "watchdog": "system", "hw": "system"}
    if drone_type not in aliases:
        raise ValueError("Only research, market or system jobs are supported")
    kind = aliases[drone_type]
    if type(interval) is not int or not 5 <= interval <= 60 or type(iterations) is not int or not 1 <= iterations <= 10:
        raise ValueError("Use 1–10 iterations and 5–60 second intervals; indefinite monitoring is disabled")
    if (iterations - 1) * interval > 90:
        raise ValueError("Sampling waits exceed the 90-second budget")
    if kind == "market" and target not in {"BTC", "ETH", "SOL", "DOGE"}:
        raise ValueError("Supported market tickers: BTC ETH SOL DOGE; no stock-price fallback")
    job = get_service().submit(f"swarm_{kind}", lambda ctx: _sample_job(ctx, kind, target, interval, iterations),
                               seconds=120, call_limit=iterations)
    return json.dumps({"job": job, "note": "Submission alone does not certify completion; inspect job state. Cooperative cancellation only; no automatic notifications."})


def swarm_parallel_execute(directive: str, subtasks=None, player=None, speak=None) -> str:
    directive = _text(directive)
    if subtasks is not None and (not isinstance(subtasks, list) or not 1 <= len(subtasks) <= 3):
        raise ValueError("Use one to three explicit subquestions")
    missions = [_text(item) for item in subtasks] if subtasks else [
        _text(f"Evidence and primary sources: {directive}"),
        _text(f"Alternatives and limitations: {directive}"),
        _text(f"Implementation constraints: {directive}")]
    job = get_service().submit("swarm_research", lambda ctx: _research_job(ctx, missions), seconds=120, call_limit=len(missions))
    return json.dumps({"job": job, "note": "Background sequential collection submitted; inspect job state. Not independently verified. No Telegram notification sent. Use status with the exact job ID."})


def list_drones() -> str:
    return json.dumps({"jobs": get_service().list(), "note": "Persisted job states, not simulated fleet telemetry."})


def get_drone_status(drone_id: str) -> str:
    return json.dumps(get_service().get(drone_id))


def kill_drone(drone_id: str) -> str:
    # No fuzzy matches and no implicit kill-all on an empty argument.
    return json.dumps({"job": get_service().cancel(drone_id),
                       "note": "Cancellation request recorded; not a claim of worker termination or effect rollback."})


def list_drone_reports(report_name=None) -> str:
    from ultron.core.report_sharing import read_report
    if report_name:
        return read_report(_REPORTS_DIR, report_name)
    files, scanned, scan_capped = [], 0, False
    if _REPORTS_DIR.is_dir():
        with os.scandir(_REPORTS_DIR) as entries:
            for entry in entries:
                scanned += 1
                if scanned > 1000:
                    scan_capped = True
                    break
                if entry.name.endswith(".md") and entry.is_file(follow_symlinks=False):
                    files.append(entry.name)
    return json.dumps({"reports": sorted(files)[:100], "truncated": scan_capped or len(files) > 100,
                       "limit": 100, "scan_limit": 1000, "note": "Exact filenames only; no fuzzy path matching. Listing is not newest-first."})


def drone_swarm(action: str = "list", drone_type: str = "research", target: str = "", directive: str = "",
                drone_id: str = "", interval: int = 30, iterations: int = 1, report_name: str = "",
                subtasks=None, receiver: str = "", player=None, speak=None, **kwargs) -> str:
    try:
        act = _text(action, 40).lower()
        if act == "share_report":
            from ultron.core.report_sharing import read_report, request_telegram_share
            return request_telegram_share(receiver, read_report(_REPORTS_DIR, report_name))
        if act in {"parallel", "parallel_swarm", "swarm", "converge", "multi_agent", "workers"}:
            return swarm_parallel_execute(directive or target, subtasks=subtasks)
        if act in {"launch", "deploy", "spawn", "create", "start"}:
            return launch_drone(drone_type, target or directive, interval, iterations)
        if act in {"list", "fleet", "registry", "all", "units"}:
            return list_drones()
        if act in {"status", "telemetry", "inspect", "logs"}:
            return get_drone_status(drone_id or target)
        if act in {"kill", "terminate", "stop", "recall"}:
            return kill_drone(drone_id or target)
        if act in {"reports", "dossier", "read", "archive"}:
            return list_drone_reports(report_name)
        raise ValueError("Unknown swarm action; no implicit launch from a directive")
    except ValueError:
        return "Swarm request rejected: check exact IDs, action, finite budgets, type/ticker and capacity. Nothing new approved."
    except Exception:
        return "Swarm unavailable. Inspect job status before retrying; no automatic retry."


TOOL = {'name': 'drone_swarm',
 'argument_mode': 'keywords',
 'description': 'Bounded journaled background collection jobs. At most two active host jobs. '
                'Launch returns a job ID, not completion. parallel_swarm is a compatibility alias '
                'for sequential up-to-three-question source collection, not independent '
                'multi-agent reasoning, verified consensus or convergence. Status/cancel use exact '
                'IDs. Cancellation is cooperative; blocked/overdue calls retain capacity. Reports '
                'are local, unverified; no automatic notifications. share_report separately '
                'requests HUD approval through the verified Telegram outbox.',
 'parameters': {'type': 'OBJECT',
                'properties': {'action': {'type': 'STRING',
                                          'description': 'launch | parallel_swarm (bounded '
                                                         'sequential background research, not '
                                                         'independent agents) | list | status | '
                                                         'kill (request cancellation) | reports | '
                                                         'share_report (HUD approval)'},
                               'directive': {'type': 'STRING',
                                             'description': 'Complex objective or inquiry to '
                                                            'decompose and execute across parallel '
                                                            'sub-agents'},
                               'drone_type': {'type': 'STRING',
                                              'description': 'research | market (BTC ETH SOL DOGE '
                                                             'only) | system'},
                               'target': {'type': 'STRING',
                                          'description': 'Research topic, crypto/stock ticker '
                                                         '(BTC, ETH, NVDA), or watch target'},
                               'drone_id': {'type': 'STRING',
                                            'description': 'Exact full host-issued background job '
                                                           'ID; no fuzzy IDs or implicit kill-all'},
                               'interval': {'type': 'INTEGER',
                                            'description': '5–60 seconds; total sampling waits at '
                                                           'most 90 seconds'},
                               'iterations': {'type': 'INTEGER',
                                              'description': 'Finite sample count 1–10; no '
                                                             'zero/indefinite loops'},
                               'receiver': {'type': 'STRING',
                                            'description': 'Explicit numeric Telegram chat ID for '
                                                           'share_report only; no default '
                                                           'recipient.'},
                               'report_name': {'type': 'STRING',
                                               'description': 'Specific markdown report filename '
                                                              'to read'},
                               'subtasks': {'type': 'ARRAY',
                                            'items': {'type': 'STRING'},
                                            'description': 'Optional one to three bounded research '
                                                           'subquestions; no recursive workers'}},
                'required': ['action']},
    'handler': drone_swarm,
}
