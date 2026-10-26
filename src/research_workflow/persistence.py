import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
from bson import BSON

from src.ops.finmind_usage import fetch_usage

from .registry import digest, file_hash, save_new
from .sources import import_finmind

DATASETS = ("TaiwanStockDelisting", "TaiwanStockSplitPrice", "TaiwanStockParValueChange")
COLLECTION = "quant_source_evidence"


def capture_finmind(output, token, session=None, usage_fn=fetch_usage):
    if not token:
        raise ValueError("FinMind credential unavailable")
    usage = usage_fn(token)
    if usage is None or usage[1] - usage[0] < len(DATASETS) + 10:
        raise ValueError("FinMind quota unavailable or insufficient; no dataset requests made")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    session = requests.Session() if session is None else session
    result = {"captured_at": datetime.now(UTC).isoformat(), "quota_before": list(usage),
              "complete_coverage_certified": False, "checks": []}
    for dataset in DATASETS:
        params = {"dataset": dataset}
        try:
            reply = session.get("https://api.finmindtrade.com/api/v4/data", params=params,
                                headers={"Authorization": f"Bearer {token}"}, timeout=45)
        except requests.RequestException as exc:
            save_new(output / "failure.json", {"dataset": dataset, "error": type(exc).__name__})
            raise ValueError("FinMind network request failed; no database write") from None
        content = reply.content.replace(token.encode(), b"[REDACTED]")
        path = output / f"{dataset}.response.json"
        with path.open("xb") as stream:
            stream.write(content)
        try:
            body = json.loads(content)
        except (ValueError, UnicodeError):
            body = None
        if (reply.status_code != 200 or not isinstance(body, dict)
                or body.get("status") != 200 or not isinstance(body.get("data"), list)):
            save_new(output / "failure.json", {"dataset": dataset, "http_status": reply.status_code,
                                               "error": "supplier response rejected"})
            raise ValueError("FinMind response rejected; collection stopped without database write")
        result["checks"].append({"dataset": dataset, "request": params, "http_status": reply.status_code,
                                 "raw_sha256": file_hash(path), "rows": len(body["data"])})
    save_new(output / "result.json", result)
    return result


def persist_snapshot(directory, db=None, apply=False):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
    expected = {"raw/supplier_result.json", *(f"raw/{dataset}.response.json" for dataset in DATASETS)}
    artifacts = manifest["artifacts"]
    if len(artifacts) != len(expected) or {row["path"] for row in artifacts} != expected:
        raise ValueError("unexpected evidence artifact paths")
    native = {}
    for artifact in artifacts:
        path = directory / artifact["path"]
        if file_hash(path) != artifact["sha256"]:
            raise ValueError("evidence artifact hash mismatch")
        native[path.name] = path.read_bytes()
    with TemporaryDirectory(prefix="quant_evidence_verify_") as temporary:
        root = Path(temporary)
        receipts = root / "receipts"
        receipts.mkdir()
        for name, content in native.items():
            target = receipts / ("result.json" if name == "supplier_result.json" else name)
            with target.open("xb") as stream:
                stream.write(content)
        validated = root / "validated"
        result = import_finmind(validated, receipts, manifest["start"], manifest["end"])
        if result["status"] == "no_data":
            raise ValueError("no supplier evidence to persist")
        recomputed_evidence = json.loads((validated / "evidence.json").read_text(encoding="utf-8"))
        recomputed_manifest = json.loads((validated / "manifest.json").read_text(encoding="utf-8"))
        if digest(evidence) != digest(recomputed_evidence) or digest(manifest) != digest(recomputed_manifest):
            raise ValueError("evidence does not match verified source reconstruction")
    payload = {"schema_version": 1, "certified_complete": False, "evidence": evidence,
               "manifest": manifest, "raw": {name: json.loads(content) for name, content in native.items()}}
    snapshot_id = digest(payload)
    document = {"_id": snapshot_id, **payload, "stored_at": datetime.now(UTC)}
    if len(BSON.encode(document)) > 15_000_000:
        raise ValueError("source snapshot exceeds safe document size")
    response = {"status": "dry_run", "snapshot_id": snapshot_id, "collection": COLLECTION,
                "evidence_status": result["status"], "certified_complete": False,
                "delisting_facts": result["delisting_facts"], "reference_events": result["reference_events"],
                "unresolved": result["unresolved"]}
    if apply:
        if db is None:
            from src.config import get_db

            db = get_db(serverSelectionTimeoutMS=10000)
        write = db[COLLECTION].update_one({"_id": snapshot_id}, {"$setOnInsert": document}, upsert=True)
        response["status"] = "stored" if write.upserted_id is not None else "already_present"
    return response