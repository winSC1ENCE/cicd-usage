import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import runner_usage as ru


def job(name="t", duration=60, tags=(), shared=True, desc=""):
    return {
        "name": name,
        "stage": "test",
        "status": "success",
        "duration": duration,
        "tag_list": list(tags),
        "runner": {"is_shared": shared, "description": desc},
    }


@pytest.mark.parametrize(
    ("kwargs", "factor"),
    [
        ({}, 1),
        ({"tags": ["saas-linux-medium-amd64"]}, 2),
        ({"desc": "1-green.saas-linux-large-arm64.runners-manager.gitlab.com/default"}, 3),
        ({"tags": ["saas-linux-2xlarge-amd64"]}, 12),
        ({"tags": ["saas-linux-medium-amd64-gpu-standard"]}, 7),
        ({"tags": ["saas-macos-medium-m1"]}, 6),
        ({"shared": False}, 0),
        ({"tags": ["saas-linux-huge-amd64"]}, None),
    ],
)
def test_cost_factor(kwargs, factor):
    assert ru.cost_factor(job(**kwargs)) == factor


def test_job_minutes_uses_duration_and_factor():
    assert ru.job_minutes(job(duration=90, tags=["saas-linux-medium-amd64"])) == pytest.approx(3.0)
    assert ru.job_minutes(job(duration=None)) == 0.0


def test_classify():
    assert ru.classify({"source": "merge_request_event", "ref": "x"}, "main") == "merge_request"
    assert ru.classify({"source": "schedule", "ref": "main"}, "main") == "schedule"
    assert ru.classify({"source": "push", "ref": "main"}, "main") == "default_branch"
    assert ru.classify({"source": "push", "ref": "feat"}, "main") == "other"


def runs():
    return [
        ({"id": 1, "source": "merge_request_event", "ref": "r"}, [job("a", 120), job("b", 60)]),
        ({"id": 2, "source": "merge_request_event", "ref": "r"}, [job("a", 60)]),
        ({"id": 3, "source": "push", "ref": "main"}, [job("a", 60, ["saas-linux-medium-amd64"])]),
    ]


def test_aggregate_and_projection():
    result = ru.aggregate(runs(), "main")
    assert result["types"]["merge_request"] == {"pipelines": 2, "minutes": pytest.approx(4.0)}
    assert result["types"]["default_branch"]["minutes"] == pytest.approx(2.0)
    assert result["jobs"]["a"]["runs"] == 3
    # 2 min avg per MR pipeline * 10 + 2 min per main pipeline * 5
    assert ru.project(result, {"merge_request": 10, "default_branch": 5}) == pytest.approx(30.0)


def test_report_mentions_quota_and_unknown_runners():
    unknown = [({"id": 9, "source": "push", "ref": "main"}, [job(tags=["saas-linux-huge-amd64"])])]
    report = ru.render_markdown(ru.aggregate(unknown, "main"), 30, 400, None)
    assert "Kontingent" in report and "ohne bekannten Kostenfaktor" in report


def test_collect_uses_api_and_paginates():
    class FakeApi:
        def get(self, path, params=None):
            return {"default_branch": "main"}

        def paginate(self, path, params=None):
            if path == "/pipelines":
                return [{"id": 1, "source": "push", "ref": "main"}]
            return [job("a", 60)]

    collected, default = ru.collect(FakeApi(), datetime.now(UTC))
    assert default == "main" and collected[0][1][0]["name"] == "a"


def test_paginate_collects_all_pages():
    api = ru.GitLab("https://gitlab.example/api/v4", "t", "g/p")
    pages = [[{"i": n} for n in range(100)], [{"i": 100}]]
    api.get = lambda path, params=None: pages[params["page"] - 1]
    assert len(api.paginate("/pipelines")) == 101


def test_main_requires_credentials(monkeypatch, capsys):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert ru.main([]) == 2
    assert "GITLAB_TOKEN" in capsys.readouterr().err
