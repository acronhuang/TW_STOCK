import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .core import combine_sleeves, core_backtest
from .diagnostics import signal_diagnostics
from .engine import backtest, prepare, signal_universe, strategy_scores, validate_config
from .metrics import deflated_sharpe, funnel, nw_t, summarize
from .registry import (
    append_attempt,
    canonical,
    check_evaluation,
    digest,
    file_hash,
    read_attempts,
    register,
    save_new,
    verify,
)
from .search import generate, neighbors


def initialize(directory, rules, source):
    directory, source = Path(directory), Path(source)
    periods = [rules[name] for name in ("search", "validation", "evaluation")]
    parsed = [date.fromisoformat(value) for period in periods for value in period]
    if parsed != sorted(set(parsed)) or rules["cutoff"] != rules["evaluation"][1]:
        raise ValueError("periods must be ordered, disjoint and end at the fixed cutoff")
    if parsed[4] <= datetime.now(ZoneInfo("Asia/Taipei")).date() and not rules.get("historical_research", True):
        raise ValueError("already observable history cannot be registered as blind")
    if rules.get("rounds", 0) < 1 or rules.get("configs_per_round", 0) < 1:
        raise ValueError("research budgets must be positive")
    if len(rules["random_seeds"]) != len(set(rules["random_seeds"])) or 43 not in rules["random_seeds"]:
        raise ValueError("random seeds must be unique and include primary control 43")
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / "data"
    data.mkdir()
    paths = {stage: data / f"{stage}.csv" for stage in ("search", "validation", "evaluation")}
    for chunk in pd.read_csv(source, dtype={"symbol": str}, chunksize=100000):
        stamps = pd.to_datetime(chunk["date"])
        for stage, path in paths.items():
            selected = chunk[stamps <= pd.Timestamp(rules[stage][1])]
            if not selected.empty:
                selected.to_csv(path, mode="a" if path.exists() else "x", header=not path.exists(), index=False)
    for stage, path in paths.items():
        if not path.exists():
            raise ValueError(f"no data for {stage}")
    recorded = {**rules, "artifacts": {stage: {"path": str(path.relative_to(directory)), "hash": file_hash(path)}
                                       for stage, path in paths.items()}}
    result = register(directory, recorded, source)
    (directory / "plans").mkdir()
    (directory / "results").mkdir()
    return result


def registration(directory):
    directory = Path(directory)
    record = json.loads((directory / "registration.json").read_text(encoding="utf-8"))
    record = verify(directory, record["source"])
    for artifact in record["rules"]["artifacts"].values():
        if file_hash(directory / artifact["path"]) != artifact["hash"]:
            raise ValueError("stage data fingerprint changed")
    return record


def plans(directory):
    result = []
    for path in sorted((Path(directory) / "plans").glob("*.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        checksum = plan.pop("plan_hash", None)
        if digest(plan) != checksum:
            raise ValueError("proposal fingerprint changed")
        plan["plan_hash"] = checksum
        result.append(plan)
    return result


def ensure_unlocked(directory):
    if (Path(directory) / "shortlist.json").exists():
        raise ValueError("study is locked; no more search, proposals or screening")


def propose(directory, group, round_number, configs, hypothesis):
    directory = Path(directory)
    ensure_unlocked(directory)
    record = registration(directory)
    rules = record["rules"]
    if not re.fullmatch(r"A|B|monkey_\d+", group) or not hypothesis.strip():
        raise ValueError("explicit research group and prior hypothesis required")
    if not 1 <= round_number <= rules["rounds"] or len(configs) != rules["configs_per_round"]:
        raise ValueError("proposal must match the registered round and configuration budget")
    occupied = {canonical(config) for plan in plans(directory) for config in plan["configs"]}
    for config in configs:
        validate_config(config)
        if set(config) != {"factor", "window", "hold", "slots", "rebalance", "reverse", "threshold"}:
            raise ValueError("only semantic configuration fields are permitted")
        key = canonical(config)
        if key in occupied:
            raise ValueError("duplicate configuration across research groups")
        occupied.add(key)
    proposal = {"group": group, "round": round_number, "configs": configs, "hypothesis": hypothesis,
                "registration": digest(record)}
    proposal["plan_hash"] = digest(proposal)
    save_new(directory / "plans" / f"{group}_{round_number}.json", proposal)
    return proposal


def controls(directory):
    record = registration(directory)
    rules = record["rules"]
    all_plans = plans(directory)
    ai = [plan for plan in all_plans if plan["group"] == "A"]
    if {plan["round"] for plan in ai} != set(range(1, rules["rounds"] + 1)):
        raise ValueError("all registered A rounds are required before fixing random budgets")
    occupied = {canonical(config) for plan in all_plans for config in plan["configs"]}
    created = []
    for seed in rules["random_seeds"]:
        group = f"monkey_{seed}"
        for round_number in range(1, rules["rounds"] + 1):
            existing = [plan for plan in all_plans if plan["group"] == group and plan["round"] == round_number]
            if existing:
                created.extend(existing)
                continue
            configs = generate(seed * 1000 + round_number, rules["configs_per_round"], occupied)
            created.append(propose(directory, group, round_number, configs, "固定種子；不根據收益選配置"))
            occupied.update(canonical(config) for config in configs)
    return created


def load_stage(directory, record, stage, include_core=False):
    artifact = record["rules"]["artifacts"][stage]
    frame = pd.read_csv(Path(directory) / artifact["path"], dtype={"symbol": str})
    if pd.to_datetime(frame["date"]).max() > pd.Timestamp(record["rules"][stage][1]):
        raise ValueError("stage boundary violation")
    core = record["rules"].get("core", {})
    if core.get("enabled") and not include_core:
        frame = frame[~frame["symbol"].isin([core["risk_symbol"], core["defensive_symbol"]])]
    return prepare(frame, record["rules"].get("strict_tradability", True))


def valid_result(directory, row):
    if row.get("status") != "ok":
        return None
    path = Path(directory) / row["artifact"]
    try:
        if file_hash(path) != row["artifact_hash"]:
            return None
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["config_hash"] != row["config_hash"] or result["stage"] != row["stage"]:
            return None
        return result
    except (OSError, ValueError, KeyError):
        return None


def task_key(row):
    return row["group"], row["config_hash"], row["stage"], row.get("probe_of", "")


def latest(directory):
    return {task_key(row): row for row in read_attempts(Path(directory) / "ledger.jsonl")}


def execute(directory, record, group, config, stage, panel, benchmark, probe_of="", capital=None):
    directory = Path(directory)
    identity = {"group": group, "config": config, "config_hash": digest(config), "stage": stage,
                "probe_of": probe_of, "registration": digest(record),
                "capital": record["rules"]["initial_cash"] if capital is None else capital}
    prior = latest(directory).get(task_key(identity))
    if stage != "evaluation" and prior and valid_result(directory, prior):
        return prior
    try:
        rules = {**record["rules"], "initial_cash": identity["capital"]}
        result = backtest(panel, config, rules, *rules[stage])
        metrics = summarize(result["dates"], result["returns"], benchmark["returns"], len(result["trades"]), rules.get("annual_days", 250))
        result.update(identity, metrics=metrics, benchmark_returns=benchmark["returns"],
                      benchmark_exposure=float(np.mean(benchmark["exposure"])))
        result["signal_diagnostics"] = signal_diagnostics(panel, strategy_scores(panel, config, rules), config, *rules[stage], signal_universe(panel, rules))
        artifact = Path("results") / f"{group}_{stage}_{uuid.uuid4().hex}.json"
        save_new(directory / artifact, result)
        attempt = {**identity, "status": "ok", "artifact": str(artifact),
                   "artifact_hash": file_hash(directory / artifact), "metrics": metrics}
    except (ValueError, TypeError, ArithmeticError, OSError, KeyError, RuntimeError, MemoryError) as exc:
        attempt = {**identity, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return append_attempt(directory / "ledger.jsonl", attempt)


def baseline(panel, record, stage):
    config = {"factor": "momentum", "window": 20, "hold": 20, "slots": 10,
              "rebalance": 20, "reverse": False, "threshold": 0.0}
    return backtest(panel, config, record["rules"], *record["rules"][stage], benchmark=True)


def run_group(directory, group, round_number):
    ensure_unlocked(directory)
    record = registration(directory)
    selected = [plan for plan in plans(directory) if plan["group"] == group and plan["round"] == round_number]
    if len(selected) != 1 or selected[0]["registration"] != digest(record):
        raise ValueError("registered proposal not found or modified")
    panel = load_stage(directory, record, "search")
    benchmark = baseline(panel, record, "search")
    return [execute(directory, record, group, config, "search", panel, benchmark) for config in selected[0]["configs"]]


def first_four(metrics):
    return funnel(metrics, {}, None, None, None)["cumulative"]["L4"]


def screen(directory):
    ensure_unlocked(directory)
    record = registration(directory)
    search = load_stage(directory, record, "search")
    search_base = baseline(search, record, "search")
    validation, validation_base = None, None
    for plan in plans(directory):
        for config in plan["configs"]:
            group, identity = plan["group"], digest(config)
            row = latest(directory).get((group, identity, "search", ""))
            result = valid_result(directory, row) if row else None
            if not result or not first_four(result["metrics"]):
                continue
            outcomes = []
            for neighbor in neighbors(config):
                probe = execute(directory, record, group, neighbor, "search", search, search_base, identity)
                outcomes.append(first_four(probe["metrics"]) if probe["status"] == "ok" else None)
            if not outcomes or None in outcomes or sum(outcomes) / len(outcomes) < 0.7:
                continue
            if validation is None:
                validation = load_stage(directory, record, "validation")
                validation_base = baseline(validation, record, "validation")
            execute(directory, record, group, config, "validation", validation, validation_base)
    return report(directory)


def report(directory):
    directory = Path(directory)
    record = registration(directory)
    rules = record["rules"]
    all_plans = plans(directory)
    attempts = read_attempts(directory / "ledger.jsonl")
    current = latest(directory)
    expected_groups = ["A", "B", *[f"monkey_{seed}" for seed in rules["random_seeds"]]]
    missing_groups = [group for group in expected_groups if
                      {plan["round"] for plan in all_plans if plan["group"] == group} != set(range(1, rules["rounds"] + 1))]
    counts = {group: {"attempts": sum(row["group"] == group for row in attempts),
                      "errors": sum(row["group"] == group and row["status"] == "error" for row in attempts),
                      "base_configs": sum(len(plan["configs"]) for plan in all_plans if plan["group"] == group)}
              for group in expected_groups}
    candidates, complete = [], not missing_groups
    for plan in all_plans:
        for config in plan["configs"]:
            group, identity = plan["group"], digest(config)
            row = current.get((group, identity, "search", ""))
            train = valid_result(directory, row) if row else None
            row = current.get((group, identity, "validation", ""))
            validation = valid_result(directory, row) if row else None
            probe_values = None
            if train and first_four(train["metrics"]):
                probe_values = []
                for neighbor in neighbors(config):
                    probe = current.get((group, digest(neighbor), "search", identity))
                    valid = valid_result(directory, probe) if probe else None
                    probe_values.append(first_four(valid["metrics"]) if valid else None)
                if not probe_values or None in probe_values or sum(probe_values) / len(probe_values) >= 0.7 and validation is None:
                    complete = False
            if train is None:
                complete = False
            combined = None
            if train and validation:
                combined = np.r_[np.array(train["returns"]) - train["benchmark_returns"],
                                 np.array(validation["returns"]) - validation["benchmark_returns"]]
            relevant = [row for row in attempts if row["group"] in (("A", "B") if group in ("A", "B") else (group,))]
            sharpes = [row.get("metrics", {}).get("daily_sr") for row in relevant if row["stage"] == "search"]
            dsr = deflated_sharpe(combined, sharpes, len(relevant)) if combined is not None else None
            metrics = dict(train["metrics"]) if train else {}
            if combined is not None:
                metrics["nw_t"] = nw_t(combined)
            ranking = min(metrics.get("ir") or -1e30, validation["metrics"].get("ir") or -1e30) if validation else -1e30
            candidates.append({"id": identity, "group": group, "config": config, "train": metrics,
                               "validation": validation["metrics"] if validation else {}, "neighbors": probe_values,
                               "dsr": dsr, "ranking": ranking, "excess": combined,
                               "execution_verified": bool(train and train["execution_verified"]),
                               "signal_diagnostics": train.get("signal_diagnostics") if train else None,
                               "baseline_exposure": train.get("benchmark_exposure") if train else None})
    retained = []
    for candidate in sorted(candidates, key=lambda item: (-item["ranking"], item["id"])):
        preliminary = funnel(candidate["train"], candidate["validation"], candidate["neighbors"], None, candidate["dsr"])
        correlation = None
        if preliminary["cumulative"]["L6"] and candidate["excess"] is not None:
            correlations = []
            for other in retained:
                if len(other) != len(candidate["excess"]) or np.std(other) == 0 or np.std(candidate["excess"]) == 0:
                    correlations.append(np.nan)
                else:
                    correlations.append(float(np.corrcoef(candidate["excess"], other)[0, 1]))
            correlation = max(correlations) if correlations and np.isfinite(correlations).all() else (0.0 if not correlations else None)
            if correlation is not None and correlation < 0.7:
                retained.append(candidate["excess"])
        candidate.update(funnel(candidate["train"], candidate["validation"], candidate["neighbors"], correlation, candidate["dsr"]))
        candidate["correlation"] = correlation
        candidate.pop("excess")
        if not complete or not candidate["execution_verified"]:
            candidate["grade"] = "research_only"
    layer_counts = {group: {layer: sum(row["group"] == group and row["cumulative"][layer] for row in candidates)
                           for layer in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")}
                    for group in expected_groups}
    return {"historical_research": record["historical_research"], "study_complete": complete,
            "counts": counts, "missing_groups": missing_groups, "layer_counts": layer_counts,
            "candidates": candidates, "qualified": [row["id"] for row in candidates if row["grade"] == "qualified"],
            "limitations": ["歷史再研究不是未知資料驗證；不變更既有前瞻研究。",
                            "DSR 試驗數含錯誤、重試與鄰域，不等於有效獨立試驗數。",
                            "同成本等權基準受整股與資金限制；須檢查實際投入比例。",
                            "可交易欄位與歷史股票池需另核對來源；缺少下市結算不假定零價。",
                            "產業中性化需當時可知分類；IC 分層是訊號診斷，不是可成交績效。",
                            "60/40 底倉需事前登記 ETF、費稅及完整歷史資料；未啟用不代表已檢驗。"]}


def lock(directory, candidate_ids, allow_research_only=False):
    directory = Path(directory)
    record = registration(directory)
    snapshot = report(directory)
    lookup = {candidate["id"]: candidate for candidate in snapshot["candidates"]}
    if not candidate_ids or len(candidate_ids) != len(set(candidate_ids)) or any(identity not in lookup for identity in candidate_ids):
        raise ValueError("explicit unique candidate IDs required")
    selected = [lookup[identity] for identity in candidate_ids]
    if not allow_research_only and any(row["grade"] != "qualified" for row in selected):
        raise ValueError("only qualified candidates may be locked without --allow-research-only")
    if any(not row["train"] for row in selected):
        raise ValueError("candidate has no successful search result")
    result = {"registration": digest(record), "candidates": selected, "report_hash": digest(snapshot),
              "ledger_hash": file_hash(directory / "ledger.jsonl"), "research_only": allow_research_only,
              "portfolio": record["rules"].get("core", {"enabled": False})}
    save_new(directory / "shortlist.json", result)
    return result


def evaluate(directory):
    directory = Path(directory)
    if (directory / "evaluation_started.json").exists():
        raise FileExistsError("evaluation was already opened; no rerun")
    record = registration(directory)
    check_evaluation(record)
    path = directory / "shortlist.json"
    if not path.exists():
        raise ValueError("lock the shortlist before evaluation")
    locked = json.loads(path.read_text(encoding="utf-8"))
    if locked["registration"] != digest(record) or file_hash(directory / "ledger.jsonl") != locked["ledger_hash"]:
        raise ValueError("locked research state changed")
    save_new(directory / "evaluation_started.json", {"lock_hash": file_hash(path)})
    panel = load_stage(directory, record, "evaluation")
    benchmark = baseline(panel, record, "evaluation")
    outcomes = [execute(directory, record, row["group"], row["config"], "evaluation", panel, benchmark)
                for row in locked["candidates"]]
    successful = [valid_result(directory, row) for row in outcomes if row["status"] == "ok"]
    portfolio = None
    if len(successful) == len(outcomes):
        navs = np.array([np.cumprod(1 + np.array(row["returns"])) for row in successful])
        nav = navs.mean(axis=0)
        returns = nav / np.r_[1.0, nav[:-1]] - 1
        portfolio = {"construction": "equal_initial_capital_buy_and_hold_sleeves",
                     "metrics": summarize(benchmark["dates"], returns, benchmark["returns"],
                                          sum(len(row["trades"]) for row in successful)),
                     "dates": benchmark["dates"], "returns": returns.tolist()}
    result = {"historical_research": record["historical_research"], "research_only": locked["research_only"],
              "candidates": outcomes, "portfolio": portfolio}
    if record["rules"].get("core", {}).get("enabled"):
        core_panel = load_stage(directory, record, "evaluation", include_core=True)
        core_result = core_backtest(core_panel, record["rules"], *record["rules"]["evaluation"])
        cohorts = {}
        for candidate in locked["candidates"]:
            cohort = "AI" if candidate["group"] in ("A", "B") else candidate["group"]
            cohorts.setdefault(cohort, []).append(candidate)
        result["portfolios"] = {}
        for cohort, candidates in cohorts.items():
            capital = record["rules"]["initial_cash"] * 0.4 / len(candidates)
            attempts = [execute(directory, record, candidate["group"], candidate["config"], "evaluation",
                                panel, benchmark, probe_of=f"funded:{cohort}", capital=capital) for candidate in candidates]
            funded = [valid_result(directory, attempt) for attempt in attempts if attempt["status"] == "ok"]
            if len(funded) == len(attempts):
                combined = combine_sleeves(core_result, funded, record["rules"]["initial_cash"])
                combined["status"] = "ok"
                combined["metrics"] = summarize(combined["dates"], combined["returns"], benchmark["returns"],
                                                  len(core_result["trades"]) + sum(len(sleeve["trades"]) for sleeve in funded))
            else:
                combined = {"status": "error", "error": "satellite allocation incomplete"}
            combined.update(core=core_result, satellites=attempts)
            result["portfolios"][cohort] = combined
    save_new(directory / "evaluation.json", result)
    return result