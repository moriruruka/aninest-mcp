"""Offline / online evaluation for the art-search pipeline.

Offline (default) scores the tag compiler against ``eval/art_cases.json``:
tag recall, tag precision and field accuracy. It never touches the network, so
it can run in CI and in a pre-commit hook.

Online (``--network``) additionally calls the real image board for the first
``--online-cases`` cases and reports the success rate and latency percentiles.
That is the number worth quoting: it measures the whole path, not the parser.

Usage::

    python eval/run_eval.py              # offline only
    python eval/run_eval.py --network    # + real board round-trip
    python eval/run_eval.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

# Case queries are Chinese; the default console encoding on Windows (cp1252) would
# make the report crash with UnicodeEncodeError when stdout is a pipe (CI).
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - unusual streams
            pass

from aninest.tagging import parse_request  # noqa: E402


def load_cases() -> list[dict]:
    return json.loads((HERE / "art_cases.json").read_text(encoding="utf-8"))["cases"]


def evaluate_offline(cases: list[dict]) -> dict:
    rows: list[dict] = []
    tp = fp = fn = 0
    field_hits = 0
    field_total = 0
    for case in cases:
        query = case["query"]
        if case.get("blocked"):
            try:
                parse_request(query)
            except ValueError:
                rows.append({"query": query, "status": "pass", "note": "blocked as expected"})
                tp += 0  # blocking is scored separately
                field_hits += 1
            else:
                rows.append({"query": query, "status": "fail", "note": "should be blocked"})
            field_total += 1
            continue

        try:
            parsed = parse_request(query)
        except ValueError as exc:
            rows.append({"query": query, "status": "fail", "note": f"unexpected rejection: {exc}"})
            continue

        expected = [tag.lower() for tag in case.get("expect_tags", [])]
        got = set(parsed.tags)
        hits = [tag for tag in expected if tag in got]
        misses = [tag for tag in expected if tag not in got]
        extras = [tag for tag in parsed.tags if tag not in expected]
        tp += len(hits)
        fn += len(misses)
        fp += len(extras)

        checks: list[str] = []
        for field in ("count", "size", "orientation"):
            if field in case:
                field_total += 1
                if getattr(parsed, field) == case[field]:
                    field_hits += 1
                    checks.append(f"{field}=ok")
                else:
                    checks.append(f"{field}={getattr(parsed, field)} (want {case[field]})")
        passed = not misses and all("want" not in check for check in checks)
        rows.append(
            {
                "query": query,
                "status": "pass" if passed else "fail",
                "tags": parsed.tags,
                "misses": misses,
                "extras": extras,
                "note": "; ".join(checks),
            }
        )

    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    return {
        "cases": len(cases),
        "passed": sum(1 for row in rows if row["status"] == "pass"),
        "tag_recall": round(recall, 3),
        "tag_precision": round(precision, 3),
        "field_accuracy": round(field_hits / field_total, 3) if field_total else 1.0,
        "rows": rows,
    }


async def evaluate_online(cases: list[dict], limit: int, count: int = 1) -> dict:
    from aninest.tools.art import search_art

    searchable = [case for case in cases if not case.get("blocked")][:limit]
    latencies: list[float] = []
    ok = 0
    failures: list[dict] = []
    for case in searchable:
        started = time.perf_counter()
        try:
            result = await search_art(case["query"], count=count)
            elapsed = time.perf_counter() - started
            latencies.append(elapsed)
            if result["count"] >= 1:
                ok += 1
            else:
                failures.append({"query": case["query"], "error": "empty result"})
        except Exception as exc:  # noqa: BLE001 - the point is to count failures
            failures.append({"query": case["query"], "error": f"{type(exc).__name__}: {exc}"})
    ordered = sorted(latencies)
    p95_index = max(0, int(len(ordered) * 0.95) - 1)
    return {
        "attempted": len(searchable),
        "succeeded": ok,
        "success_rate": round(ok / len(searchable), 3) if searchable else 0.0,
        "latency_p50_s": round(statistics.median(ordered), 2) if ordered else None,
        "latency_p95_s": round(ordered[p95_index], 2) if ordered else None,
        "failures": failures,
    }


def print_report(offline: dict, online: dict | None) -> None:
    print(f"{'query':44s} status  note")
    print("-" * 92)
    for row in offline["rows"]:
        note = row.get("note", "")
        if row["status"] == "fail" and row.get("misses"):
            note = f"missing {row['misses']} {note}".strip()
        print(f"{row['query'][:44]:44s} {row['status']:6s}  {note}")
    print("-" * 92)
    print(
        f"cases={offline['cases']} passed={offline['passed']} "
        f"recall={offline['tag_recall']} precision={offline['tag_precision']} "
        f"field_accuracy={offline['field_accuracy']}"
    )
    if online:
        print(
            f"online: {online['succeeded']}/{online['attempted']} ok="
            f"{online['success_rate']} p50={online['latency_p50_s']}s "
            f"p95={online['latency_p95_s']}s"
        )
        for failure in online["failures"]:
            print(f"  failed: {failure['query']} -> {failure['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the AniNest art pipeline.")
    parser.add_argument("--network", action="store_true", help="also hit the real image board")
    parser.add_argument("--online-cases", type=int, default=5, help="cases to run online")
    parser.add_argument("--count", type=int, default=1, help="images per online case")
    parser.add_argument("--json", type=Path, help="write the full report to this path")
    args = parser.parse_args()

    cases = load_cases()
    offline = evaluate_offline(cases)
    online = None
    if args.network:
        online = asyncio.run(evaluate_online(cases, args.online_cases, args.count))
    print_report(offline, online)

    if args.json:
        args.json.write_text(
            json.dumps({"offline": offline, "online": online}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"report written to {args.json}")

    if offline["passed"] < offline["cases"]:
        return 1
    if online and online["success_rate"] < 0.6:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
