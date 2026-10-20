"""TDD: GPU 取樣與每 4 小時報表：取樣失敗要留缺口、時段邊界要對、50% 門檻含等於。"""

import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from scripts import gpu_report, gpu_sample

pytestmark = pytest.mark.unit


def fake_run(outputs):
    def run(cmd, **kwargs):
        host = cmd[-2]
        value = outputs[host]
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(stdout=value)

    return run


@pytest.mark.parametrize("text, expected", [
    ("37, 30210, 32768, 61\n", [37, 30210, 32768, 61]),
    ("Failed to initialize NVML: Driver/library version mismatch\n", None),
    ("37, [N/A], 32768, 61\n", None),
    ("", None),
])
def test_nvidia_smi_output_is_parsed_or_rejected(text, expected):
    assert gpu_sample.parse(text) == expected


def test_a_sample_asks_the_given_host_with_a_short_connect_timeout():
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(stdout="5, 100, 200, 40\n")

    assert gpu_sample.sample("172.16.9.28", run) == [5, 100, 200, 40]
    assert "172.16.9.28" in seen["cmd"] and "ConnectTimeout=5" in seen["cmd"] and "BatchMode=yes" in seen["cmd"]


def test_a_hung_ssh_counts_as_a_failed_sample():
    assert gpu_sample.sample("h", fake_run({"h": subprocess.TimeoutExpired("ssh", 20)})) is None


def test_main_writes_one_header_and_one_row_per_node_each_run(tmp_path):
    out = tmp_path / "gpu.csv"
    run = fake_run({"172.16.9.28": "50, 30000, 32768, 70\n", "172.16.9.27": "8, 20000, 32768, 55\n"})

    gpu_sample.main(out, now=lambda: datetime(2026, 10, 23, 21, 2, 3), run=run)
    gpu_sample.main(out, now=lambda: datetime(2026, 10, 23, 21, 4, 3), run=run)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "time,node,util_pct,mem_used_mib,mem_total_mib,temp_c"
    assert len(lines) == 5 and lines[1] == "2026-10-23 21:02:03,28,50,30000,32768,70"
    assert lines[2].startswith("2026-10-23 21:02:03,27,8,")


def test_a_failed_sample_leaves_a_blank_row_and_says_so(tmp_path, capsys):
    out = tmp_path / "gpu.csv"
    run = fake_run({"172.16.9.28": "Failed to initialize NVML\n", "172.16.9.27": "8, 20000, 32768, 55\n"})

    gpu_sample.main(out, now=lambda: datetime(2026, 10, 23, 21, 2, 3), run=run)

    assert "2026-10-23 21:02:03,28,,,," in out.read_text(encoding="utf-8")
    assert ".28 取樣失敗" in capsys.readouterr().err


ROWS = [
    (datetime(2026, 10, 24, 8, 10), "28", 10, 1024),
    (datetime(2026, 10, 24, 8, 20), "28", 90, 2048),
    (datetime(2026, 10, 24, 11, 59), "28", 50, 1024),
    (datetime(2026, 10, 24, 11, 59), "28", None, None),
    (datetime(2026, 10, 24, 12, 0), "28", 20, 4096),
    (datetime(2026, 10, 24, 8, 10), "27", 8, 512),
]


def test_samples_fall_into_four_hour_buckets_with_the_boundary_in_the_next_one():
    stats = gpu_report.summarize(ROWS, hours=4)

    morning, noon = stats[(datetime(2026, 10, 24, 8), "28")], stats[(datetime(2026, 10, 24, 12), "28")]
    assert morning["samples"] == 3 and morning["missing"] == 1
    assert morning["mean"] == pytest.approx(50) and morning["max_mem_gib"] == 2.0
    assert noon["samples"] == 1 and noon["mean"] == 20


def test_busy_share_counts_exactly_fifty_percent_as_busy():
    morning = gpu_report.summarize(ROWS, hours=4)[(datetime(2026, 10, 24, 8), "28")]

    assert morning["busy_pct"] == pytest.approx(2 / 3 * 100)


def test_p90_is_a_real_sample_not_an_average():
    rows = [(datetime(2026, 10, 24, 8, i), "28", u, 1) for i, u in enumerate([0] * 9 + [100])]

    assert gpu_report.summarize(rows)[(datetime(2026, 10, 24, 8), "28")]["p90"] == 0
    rows = [(datetime(2026, 10, 24, 8, i), "28", u, 1) for i, u in enumerate([0] * 8 + [100, 100])]
    assert gpu_report.summarize(rows)[(datetime(2026, 10, 24, 8), "28")]["p90"] == 100


def test_since_and_until_cut_the_range():
    stats = gpu_report.summarize(ROWS, since=datetime(2026, 10, 24, 12), until=datetime(2026, 10, 25))

    assert {k[0] for k in stats} == {datetime(2026, 10, 24, 12)}


def test_the_report_says_no_data_for_a_node_with_no_samples_in_a_bucket(tmp_path):
    text = gpu_report.render(gpu_report.summarize([(datetime(2026, 10, 24, 8, 10), "28", 10, 1024)]))

    assert "10-24 08:00~12:00" in text and "無資料" in text


def test_the_cli_reads_the_csv_and_reports_a_missing_file(tmp_path, capsys):
    assert gpu_report.main(["--file", str(tmp_path / "nope.csv")]) == 1
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("time,node,util_pct,mem_used_mib,mem_total_mib,temp_c\n2026-10-24 08:10:00,28,77,30000,32768,70\n", encoding="utf-8")

    assert gpu_report.main(["--file", str(csv_path)]) == 0
    assert "77%" in capsys.readouterr().out


def test_until_is_exclusive():
    rows = [(datetime(2026, 10, 24, 23, 58), "28", 10, 1), (datetime(2026, 10, 25, 0, 0), "28", 10, 1)]

    stats = gpu_report.summarize(rows, until=datetime(2026, 10, 25))

    assert {k[0] for k in stats} == {datetime(2026, 10, 24, 20)}
