"""TDD: 文件 lint——只在現行文件裡找失效路徑與過時模型名，歷史文件不碰，也不能誤報佔位符。"""

from datetime import datetime

import pytest

from scripts import docs_lint as lint

pytestmark = pytest.mark.unit

ROSTER = ["qwen3-14b:latest", "gemma2:9b", "bge-m3", "qwen2.5-14b:latest", "llama3.1:8b"]


def test_a_path_that_exists_is_fine_and_one_that_does_not_is_reported_with_its_line():
    text = "第一行\n見 `scripts/a.py` 與 `scripts/gone.py`。\n"
    assert lint.dead_refs(text, lambda ref: ref == "scripts/a.py") == [(2, "scripts/gone.py")]


@pytest.mark.parametrize("ref", ["docs/adr/NNNN-標題.md", "scripts/foo_YYYYMMDD.py", "docs/xxx.md"])
def test_placeholder_paths_are_not_reported(ref):
    assert lint.dead_refs(f"`{ref}`", lambda r: False) == []


def test_only_backticked_project_paths_count():
    text = "scripts/bare.py 沒有反引號；`https://x/scripts/a.py`；`other/dir/a.py`；`scripts/data.csv`"
    assert lint.dead_refs(text, lambda r: False) == []


def test_each_path_extension_the_docs_use_is_recognised():
    refs = ["a.py", "a.sh", "a.md", "a.json", "a.yaml", "a.service", "a.timer", "a.txt"]
    text = " ".join(f"`scripts/{r}`" for r in refs)
    assert [r for _, r in lint.dead_refs(text, lambda r: False)] == [f"scripts/{r}" for r in refs]


@pytest.mark.parametrize("name", ["hermes3:8b", "qwen2.5-3b", "foundation-sec-8b", "whiterabbitneo-7b", "gemma4:12b"])
def test_models_outside_the_current_lineup_are_reported(name):
    assert lint.stale_models(f"用 {name} 做分析", ROSTER) == [(1, name)]


@pytest.mark.parametrize(
    "text",
    ["qwen3-14b", "qwen3-14b:latest", "bge-m3:latest", "Qwen2.5-14B", "gemma2:9b。", "qwen2.5-14b，", "Hermes Agent", "Phi 是人名"],
)
def test_models_in_the_lineup_and_words_without_a_version_are_not_reported(text):
    assert lint.stale_models(text, ROSTER) == []


def test_chinese_text_touching_a_model_name_neither_hides_it_nor_joins_it():
    assert lint.stale_models("使用qwen2.5-14b模型", ROSTER) == []
    assert lint.stale_models("使用hermes3:8b模型", ROSTER) == [(1, "hermes3:8b")]


@pytest.mark.parametrize("text", ["qwen2.5", "hermes3", "qwen3.6", "llama3", "gemma2 系列"])
def test_bare_family_names_without_a_size_or_tag_are_not_checked(text):
    assert lint.stale_models(text, ROSTER) == []


def test_trailing_punctuation_does_not_hide_or_invent_a_model_name():
    assert lint.stale_models("跑過 qwen2.5-3b。", ROSTER) == [(1, "qwen2.5-3b")]


def make_repo(tmp_path):
    def write(rel, text):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    write("README.md", "見 `scripts/ok.py` 與 `scripts/missing.py`，模型 hermes3:8b")
    write("CHANGELOG.md", "`scripts/removed.py` hermes3:8b")
    write("scripts/ok.py", "")
    write("docs/guides/g.md", "`src/gone.py`")
    write("docs/架構規劃/a.md", "`src/also_gone.py`")
    write("docs/adr/0001-x.md", "`docs/adr/missing.md` hermes3:8b")
    write("docs/archive/old.md", "`scripts/old.py` qwen2.5-3b")
    write("docs/plans/p.md", "`scripts/planned.py`")
    write("docs/CHANGELOG_2026-06.md", "`scripts/removed.py`")


def test_only_living_docs_are_scanned(tmp_path):
    make_repo(tmp_path)
    names = [p.relative_to(tmp_path).as_posix() for p in lint.living_docs(tmp_path)]
    assert names == ["README.md", "docs/guides/g.md", "docs/架構規劃/a.md"]


def test_lint_reports_findings_from_living_docs_only_sorted_by_kind_file_and_line(tmp_path):
    make_repo(tmp_path)
    found = lint.lint(tmp_path, ROSTER)
    assert [(f["kind"], f["file"], f["detail"]) for f in found] == [
        ("不在現行編制的模型", "README.md", "hermes3:8b"),
        ("失效路徑", "README.md", "scripts/missing.py"),
        ("失效路徑", "docs/guides/g.md", "src/gone.py"),
        ("失效路徑", "docs/架構規劃/a.md", "src/also_gone.py"),
    ]
    assert all(f["line"] == 1 for f in found)


def test_render_groups_by_kind_with_counts_and_says_so_when_clean():
    findings = [{"kind": "失效路徑", "file": "README.md", "line": 3, "detail": "scripts/x.py"}]
    text = lint.render("2026-10-17", findings, 4)
    assert "掃描 4 份現行文件，共 1 項" in text and "## 失效路徑（1 處，1 項）" in text and "| README.md | `scripts/x.py` | 3 |" in text
    assert "沒有發現" in lint.render("2026-10-17", [], 4)


def test_repeated_findings_in_one_file_are_grouped_and_long_line_lists_are_cut():
    findings = [{"kind": "不在現行編制的模型", "file": "A.md", "line": n, "detail": "hermes3:8b"} for n in range(1, 9)]
    findings.append({"kind": "不在現行編制的模型", "file": "A.md", "line": 20, "detail": "qwen2.5-3b"})
    text = lint.render("2026-10-17", findings, 1)
    assert "（9 處，2 項）" in text
    assert "| A.md | `hermes3:8b` | 1、2、3、4、5、6 …共 8 處 |" in text
    assert "| A.md | `qwen2.5-3b` | 20 |" in text


def test_the_docs_folder_of_decision_records_is_not_scanned_even_when_it_is_stale(tmp_path):
    make_repo(tmp_path)
    assert not any(f["file"].startswith("docs/adr/") for f in lint.lint(tmp_path, ROSTER))


def run_main(tmp_path, *extra):
    make_repo(tmp_path)
    out = tmp_path / "out"
    code = lint.main(["--root", str(tmp_path), "--out-dir", str(out), *extra], roster=ROSTER, now=lambda: datetime(2026, 10, 17))
    return code, out / "report_20261017.md"


def test_main_writes_the_dated_report_and_returns_zero_by_default(tmp_path, capsys):
    code, path = run_main(tmp_path)
    assert code == 0 and "scripts/missing.py" in path.read_text(encoding="utf-8")
    assert "失效路徑 3" in capsys.readouterr().out


def test_strict_mode_fails_only_when_there_are_findings(tmp_path):
    assert run_main(tmp_path, "--strict")[0] == 1
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "README.md").write_text("沒有引用", encoding="utf-8")
    code = lint.main(["--root", str(clean), "--out-dir", str(clean / "o"), "--strict"], roster=ROSTER, now=lambda: datetime(2026, 10, 17))
    assert code == 0


def test_the_real_lineup_is_what_the_default_roster_reads():
    roster = lint.current_roster()
    assert "qwen3-14b:latest" in roster and "nomic-embed-text" not in roster


def test_a_model_name_glued_to_a_longer_identifier_is_not_reported():
    assert lint.stale_models("fooqwen2.5-3b 與 pre.hermes3:8b", ROSTER) == []


@pytest.mark.parametrize("name", ["llama3:instruct", "phi3:mini"])
def test_a_model_with_only_a_tag_and_no_size_is_still_reported(name):
    assert lint.stale_models(f"用 {name}", ROSTER) == [(1, name)]
