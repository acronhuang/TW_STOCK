"""Isolated Taiwan quant research CLI; JSON output, no database writes."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.research_workflow import workflow
from src.research_workflow.data import audit, mongo_prices, source_inventory
from src.research_workflow.evidence import enrich
from src.research_workflow.registry import canonical, save_new


def parser():
    result = argparse.ArgumentParser(description="台股研究平台；不寫正式資料庫、不變更評分或排程")
    result.add_argument("--study", type=Path, default=ROOT / "logs" / "quant_workflow")
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("import-finmind", help="離線核對既有來源回應；不推定歷史股票池或股數權利")
    command.add_argument("--receipts", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--start", default="2014-01-01")
    command.add_argument("--end", default="2026-09-18")
    command = commands.add_parser("collect", help="唯讀取得並核對官方事件；部分證據不等於完整覆蓋")
    command.add_argument("--symbols", default="2330,2317,0050,00635U")
    command.add_argument("--start", default="2026-01-01")
    command.add_argument("--end", default="2026-09-18")
    command.add_argument("--out", type=Path, required=True)
    command = commands.add_parser("sources")
    command.add_argument("--symbols", default="2330,2317,0050,00635U")
    command.add_argument("--start", default="2014-01-01")
    command.add_argument("--end", default="2026-09-18")
    for name in ("audit", "export"):
        command = commands.add_parser(name)
        command.add_argument("--prices", type=Path)
        evidence_source = command.add_mutually_exclusive_group()
        evidence_source.add_argument("--evidence", type=Path)
        evidence_source.add_argument("--snapshot", help="指定正式來源快照 ID；唯讀且不自動解除資料阻擋")
        command.add_argument("--symbols", default="2330,2317")
        command.add_argument("--start", default="2026-01-01")
        command.add_argument("--end", default="2026-09-18")
        if name == "export":
            command.add_argument("--out", type=Path, required=True)
    command = commands.add_parser("init")
    command.add_argument("--rules", type=Path, default=ROOT / "research" / "tw_quant" / "rules.json")
    command.add_argument("--prices", type=Path, required=True)
    command = commands.add_parser("propose")
    command.add_argument("--group", choices=("A", "B"), required=True)
    command.add_argument("--round", type=int, required=True)
    command.add_argument("--configs", type=Path, required=True)
    command.add_argument("--hypothesis", required=True)
    command = commands.add_parser("run")
    command.add_argument("--group", required=True)
    command.add_argument("--round", type=int, required=True)
    command = commands.add_parser("controls")
    command.add_argument("--run", action="store_true")
    commands.add_parser("screen")
    commands.add_parser("report")
    command = commands.add_parser("lock")
    command.add_argument("--candidate", action="append", required=True)
    command.add_argument("--allow-research-only", action="store_true")
    commands.add_parser("evaluate")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "import-finmind":
            from src.research_workflow.sources import import_finmind

            print(canonical(import_finmind(args.out, args.receipts, args.start, args.end)))
            return 2
        if args.command == "collect":
            from src.research_workflow.sources import collect

            print(canonical(collect(args.out, args.symbols.split(","), args.start, args.end)))
            return 2
        if args.command == "sources":
            print(canonical(source_inventory(args.symbols.split(","), args.start, args.end)))
            return 2
        if args.command in ("audit", "export"):
            frame = (pd.read_csv(args.prices, dtype={"symbol": str}) if args.prices
                     else mongo_prices(args.symbols.split(","), args.start, args.end))
            evidence = None
            if args.evidence:
                evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
            elif args.snapshot:
                from src.research_workflow.persistence import load_snapshot

                if frame.empty:
                    raise ValueError("cannot select snapshot evidence for empty prices")
                dates = pd.to_datetime(frame["date"], errors="raise")
                evidence = load_snapshot(args.snapshot, sorted(frame["symbol"].astype(str).unique()),
                                         dates.min().date().isoformat(), dates.max().date().isoformat())
            if evidence is not None:
                frame = enrich(frame, evidence)
            result = audit(frame)
            if args.snapshot:
                result["source_snapshot"] = evidence["source_snapshot"]
            if args.command == "export":
                args.out.parent.mkdir(parents=True, exist_ok=True)
                frame.to_csv(args.out, mode="x", index=False)
                save_new(args.out.with_suffix(".audit.json"), result)
                if evidence is not None:
                    save_new(args.out.with_suffix(".evidence.json"), evidence)
            print(canonical(result))
            return 0 if result["status"] == "ready_for_input_validation" else 2
        if args.command == "init":
            rules = json.loads(args.rules.read_text(encoding="utf-8"))
            result = workflow.initialize(args.study, rules, args.prices)
        elif args.command == "propose":
            configs = json.loads(args.configs.read_text(encoding="utf-8"))
            result = workflow.propose(args.study, args.group, args.round, configs, args.hypothesis)
        elif args.command == "run":
            result = workflow.run_group(args.study, args.group, args.round)
        elif args.command == "controls":
            result = workflow.controls(args.study)
            if args.run:
                result = [workflow.run_group(args.study, plan["group"], plan["round"]) for plan in result]
        elif args.command == "screen":
            result = workflow.screen(args.study)
        elif args.command == "report":
            result = workflow.report(args.study)
        elif args.command == "lock":
            result = workflow.lock(args.study, args.candidate, args.allow_research_only)
        else:
            result = workflow.evaluate(args.study)
        print(canonical(result))
        if args.command == "run" and any(row["status"] != "ok" for row in result):
            return 2
        if args.command == "controls" and args.run and any(row["status"] != "ok" for group in result for row in group):
            return 2
        if args.command == "evaluate" and any(row["status"] != "ok" for row in result["candidates"]):
            return 2
        if args.command == "evaluate" and any(row["status"] != "ok" for row in result.get("portfolios", {}).values()):
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(canonical({"status": "error", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())