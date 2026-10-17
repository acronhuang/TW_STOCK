#!/usr/bin/env python3
"""文件 lint：找「現行文件」裡已經失效的說法。只讀、只報告，不改文件。

檢查兩件事（都不需要 LLM，結果可重現）：
  1. 文件引用的檔案路徑（scripts/、src/、dashboard/ 等）在專案裡已不存在。
  2. 文件提到的模型名不在現行編制（src/moe/model_nodes.py）裡。
範圍只含現行文件：根目錄的 md（不含 CHANGELOG）、docs/guides、docs/架構規劃。
ADR 是當時的決策紀錄、不改寫；歷史紀錄、計畫、封存文件本來就會提到已不存在的東西，都不在範圍內。
互相矛盾的說法需要語意判斷，這裡不做。
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVING_DIRS = ("docs/guides", "docs/架構規劃")
EXCLUDE_ROOT = {"CHANGELOG.md"}
REF = re.compile(r"`((?:scripts|src|dashboard|tests|deploy|docs|models)/[\w./\-]+\.(?:py|sh|md|json|yaml|service|timer|txt))`")
PLACEHOLDER = re.compile(r"NNNN|YYYY|xxx|<|\*", re.IGNORECASE)
MODEL = re.compile(
    r"(?<![A-Za-z0-9.\-])(?:qwen|llama|gemma|hermes|mistral|phi|granite|deepseek|bge|nomic|foundation-sec|whiterabbitneo|lfm)"
    r"[A-Za-z0-9.\-]*(?::[A-Za-z0-9._\-]+)?",
    re.IGNORECASE,
)
SIZE_OR_TAG = re.compile(r"\d+(?:\.\d+)?b(?![a-z])|:", re.IGNORECASE)  # 只查寫明大小或標籤的模型名，不查 qwen3 這類系列名
EXTERNAL_MODELS = ()  # 編制之外但不算過時的模型名（目前沒有）


def living_docs(root):
    files = [p for p in sorted(root.glob("*.md")) if p.name not in EXCLUDE_ROOT]
    for sub in LIVING_DIRS:
        files += sorted((root / sub).glob("**/*.md"))
    return files


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def dead_refs(text, exists):
    """回 [(行號, 路徑)]：反引號包住、看起來像專案檔案、但 exists(路徑) 為假的引用。"""
    found = []
    for match in REF.finditer(text):
        ref = match.group(1)
        if not PLACEHOLDER.search(ref) and not exists(ref):
            found.append((_line(text, match.start()), ref))
    return found


def _normal(name):
    name = name.lower().rstrip(".-:")
    return name[: -len(":latest")] if name.endswith(":latest") else name


def stale_models(text, roster):
    """回 [(行號, 模型名)]：文件裡寫明大小或標籤（如 14b、:8b）的模型名、但不在 roster 的字串。"""
    known = {_normal(name) for name in roster}
    found = []
    for match in MODEL.finditer(text):
        token = match.group(0).rstrip(".-:")
        if SIZE_OR_TAG.search(token) and _normal(token) not in known:
            found.append((_line(text, match.start()), token))
    return found


def lint(root, roster):
    """回 [{kind, file, line, detail}]，依檔案與行號排序。"""
    findings = []
    for path in living_docs(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for line, ref in dead_refs(text, lambda r: (root / r).exists()):
            findings.append({"kind": "失效路徑", "file": rel, "line": line, "detail": ref})
        for line, name in stale_models(text, roster):
            findings.append({"kind": "不在現行編制的模型", "file": rel, "line": line, "detail": name})
    return sorted(findings, key=lambda f: (f["kind"], f["file"], f["line"]))


def render(stamp, findings, scanned):
    kinds = sorted({f["kind"] for f in findings})
    lines = [
        f"# 文件 lint 報告 {stamp}",
        "",
        f"掃描 {scanned} 份現行文件，共 {len(findings)} 項待複核。只讀、只報告；"
        "歷史紀錄、計畫與封存文件不在範圍內，互相矛盾的說法需人工判斷。",
    ]
    for kind in kinds:
        rows = [f for f in findings if f["kind"] == kind]
        groups = {}
        for f in rows:
            groups.setdefault((f["file"], f["detail"]), []).append(f["line"])
        lines += ["", f"## {kind}（{len(rows)} 處，{len(groups)} 項）", "", "| 檔案 | 內容 | 行號 |", "|---|---|---|"]
        for (file, detail), numbers in groups.items():
            shown = "、".join(map(str, numbers[:6])) + (f" …共 {len(numbers)} 處" if len(numbers) > 6 else "")
            lines.append(f"| {file} | `{detail}` | {shown} |")
    if not findings:
        lines += ["", "沒有發現。"]
    return "\n".join(lines) + "\n"


def current_roster():
    from src.moe import model_nodes

    return [*model_nodes.MODEL_NODES, model_nodes.EMBED_MODEL, model_nodes.ALTOS_MODEL, *EXTERNAL_MODELS]


def main(argv=None, roster=None, now=datetime.now):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "logs" / "docs_lint")
    parser.add_argument("--strict", action="store_true", help="有任何項目就以非零結束")
    args = parser.parse_args(argv)
    moment = now()
    findings = lint(args.root, roster if roster is not None else current_roster())
    report = render(f"{moment:%Y-%m-%d}", findings, len(living_docs(args.root)))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"report_{moment:%Y%m%d}.md"
    path.write_text(report, encoding="utf-8")
    counts = {}
    for finding in findings:
        counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1
    print(f"已寫入 {path}；" + ("、".join(f"{k} {n}" for k, n in counts.items()) if counts else "沒有發現"))
    return 1 if findings and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
