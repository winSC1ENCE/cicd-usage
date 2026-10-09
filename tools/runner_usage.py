#!/usr/bin/env python3
"""Estimate GitLab.com compute-minute usage of a project from its pipeline history.

Compute minutes per job = duration / 60 * cost factor (GitLab docs, "Compute minutes").
Needs a token that can read the project (scope read_api). Standard library only.

    GITLAB_TOKEN=... GITLAB_PROJECT_ID=group/project python tools/runner_usage.py --days 30
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta

# https://docs.gitlab.com/ci/pipelines/compute_minutes/ (checked 2026-10-09)
COST_FACTORS = {
    ("linux", "small"): 1,
    ("linux", "medium"): 2,
    ("linux", "large"): 3,
    ("linux", "xlarge"): 6,
    ("linux", "2xlarge"): 12,
    ("linux-gpu", "medium"): 7,
    ("macos", "medium"): 6,
    ("macos", "large"): 12,
    ("windows", "medium"): 1,
}
DEFAULT_QUOTA_MINUTES = 10_000  # GitLab Premium on GitLab.com (Free: 400)


def runner_class(job: dict) -> tuple[str, str]:
    """Return (family, size) for a job, based on runner tags/description."""
    text = " ".join([*job.get("tag_list", []), (job.get("runner") or {}).get("description", "")])
    match = re.search(
        r"saas-(linux|macos|windows)-([a-z0-9]+?)-(?:amd64|arm64|m\d\w*)(-gpu)?", text
    )
    if not match:
        return ("linux", "small")
    family, size, gpu = match.groups()
    return (f"{family}-gpu" if gpu else family, size)


def cost_factor(job: dict) -> float | None:
    """None means unknown: not a GitLab.com hosted runner we have a factor for."""
    runner = job.get("runner") or {}
    if runner and not runner.get("is_shared", True):
        return 0.0
    return COST_FACTORS.get(runner_class(job))


def job_minutes(job: dict) -> float:
    duration = job.get("duration")
    factor = cost_factor(job)
    if duration is None or factor is None:
        return 0.0
    return duration / 60 * factor


def classify(pipeline: dict, default_branch: str) -> str:
    source = pipeline.get("source", "")
    if source == "merge_request_event":
        return "merge_request"
    if source == "schedule":
        return "schedule"
    if pipeline.get("ref") == default_branch:
        return "default_branch"
    return "other"


def aggregate(runs: list[tuple[dict, list[dict]]], default_branch: str) -> dict:
    types: dict[str, dict] = defaultdict(lambda: {"pipelines": 0, "minutes": 0.0})
    jobs: dict[str, dict] = defaultdict(lambda: {"runs": 0, "minutes": 0.0, "seconds": 0.0})
    unknown = 0
    rows = []
    for pipeline, pipeline_jobs in runs:
        kind = classify(pipeline, default_branch)
        total = 0.0
        for job in pipeline_jobs:
            if job.get("duration") is not None and cost_factor(job) is None:
                unknown += 1
            minutes = job_minutes(job)
            total += minutes
            stats = jobs[job["name"]]
            stats["runs"] += 1
            stats["minutes"] += minutes
            stats["seconds"] += job.get("duration") or 0
            rows.append(
                {
                    "pipeline": pipeline["id"],
                    "type": kind,
                    "job": job["name"],
                    "stage": job.get("stage", ""),
                    "status": job.get("status", ""),
                    "seconds": round(job.get("duration") or 0, 1),
                    "runner_class": "/".join(runner_class(job)),
                    "cost_factor": cost_factor(job),
                    "compute_minutes": round(minutes, 3),
                }
            )
        types[kind]["pipelines"] += 1
        types[kind]["minutes"] += total
    return {"types": dict(types), "jobs": dict(jobs), "unknown_jobs": unknown, "rows": rows}


def parse_assumptions(text: str) -> dict[str, int]:
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        key, _, value = part.partition("=")
        out[key.strip()] = int(value)
    return out


def project(result: dict, per_month: dict[str, int]) -> float:
    total = 0.0
    for kind, count in per_month.items():
        stats = result["types"].get(kind)
        if stats and stats["pipelines"]:
            total += stats["minutes"] / stats["pipelines"] * count
    return total


def render_markdown(result: dict, days: int, quota: float, per_month: dict[str, int] | None) -> str:
    types, jobs = result["types"], result["jobs"]
    observed = sum(t["minutes"] for t in types.values())
    lines = [f"# Runner-Verbrauch (letzte {days} Tage)", ""]
    lines += [
        "| Pipeline-Typ | Pipelines | Minuten gesamt | Minuten/Pipeline |",
        "|---|---:|---:|---:|",
    ]
    for kind, t in sorted(types.items()):
        avg = t["minutes"] / t["pipelines"] if t["pipelines"] else 0
        lines.append(f"| {kind} | {t['pipelines']} | {t['minutes']:.1f} | {avg:.2f} |")
    lines += ["", f"Beobachtet: **{observed:.1f}** Compute-Minuten", ""]
    lines += ["| Job | Läufe | Ø Sekunden | Minuten gesamt |", "|---|---:|---:|---:|"]
    for name, j in sorted(jobs.items(), key=lambda kv: -kv[1]["minutes"]):
        lines.append(
            f"| {name} | {j['runs']} | {j['seconds'] / j['runs']:.0f} | {j['minutes']:.1f} |"
        )
    lines.append("")
    monthly = project(result, per_month) if per_month else observed * 30 / days
    basis = (
        "Annahme " + ", ".join(f"{k}={v}" for k, v in per_month.items())
        if per_month
        else f"Hochrechnung der letzten {days} Tage auf 30 Tage"
    )
    lines += [
        f"**Monatsprognose:** {monthly:.0f} Minuten ({basis})",
        f"**Kontingent:** {quota:.0f} Minuten, Auslastung {monthly / quota * 100:.0f} %",
    ]
    if result["unknown_jobs"]:
        note = (
            f"Hinweis: {result['unknown_jobs']} Jobs liefen auf Runnern ohne bekannten "
            "Kostenfaktor und sind mit 0 Minuten gezählt."
        )
        lines += ["", note]
    return "\n".join(lines) + "\n"


class GitLab:
    def __init__(self, api_url: str, token: str, project: str):
        self.base = f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project, safe='')}"
        self.token = token

    def get(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": self.token})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def paginate(self, path: str, params: dict | None = None) -> list:
        items: list = []
        page = 1
        while True:
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            assert isinstance(batch, list)
            items += batch
            if len(batch) < 100:
                return items
            page += 1


def collect(api, since: datetime) -> tuple[list[tuple[dict, list[dict]]], str]:
    default_branch = api.get("")["default_branch"]
    pipelines = api.paginate("/pipelines", {"updated_after": since.isoformat()})
    runs = [
        (p, api.paginate(f"/pipelines/{p['id']}/jobs", {"include_retried": "true"}))
        for p in pipelines
    ]
    return runs, default_branch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--quota",
        type=float,
        default=DEFAULT_QUOTA_MINUTES,
        help="monthly compute minutes of your plan (Premium: 10000, Free: 400)",
    )
    parser.add_argument(
        "--assume",
        help='expected pipelines per month for the projection, e.g. "merge_request=40,default_branch=20"',
    )
    parser.add_argument("--out", help="write the Markdown report to this file")
    parser.add_argument("--csv", help="write per-job rows to this CSV file")
    args = parser.parse_args(argv)

    token = os.environ.get("GITLAB_TOKEN")
    project = os.environ.get("GITLAB_PROJECT_ID") or os.environ.get("CI_PROJECT_ID")
    api_url = (
        os.environ.get("CI_API_V4_URL")
        or os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/") + "/api/v4"
    )
    if not token or not project:
        print("GITLAB_TOKEN and GITLAB_PROJECT_ID must be set", file=sys.stderr)
        return 2

    since = datetime.now(UTC) - timedelta(days=args.days)
    runs, default_branch = collect(GitLab(api_url, token, project), since)
    result = aggregate(runs, default_branch)
    report = render_markdown(
        result, args.days, args.quota, parse_assumptions(args.assume) if args.assume else None
    )
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=list(result["rows"][0]) if result["rows"] else ["pipeline"]
            )
            writer.writeheader()
            writer.writerows(result["rows"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
