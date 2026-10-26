import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def code_hash():
    root = Path(__file__).resolve().parents[1]
    files = sorted(Path(__file__).parent.glob("*.py"))
    files += sorted((root / "backtesting").glob("*.py"))
    entry = root.parent / "scripts" / "quant_workflow.py"
    if entry.exists():
        files.append(entry)
    return digest({str(path.relative_to(root.parent)): file_hash(path) for path in files})


def register(directory, rules, source):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record = {"rules": rules, "rules_hash": digest(rules), "data_hash": file_hash(source),
              "code_hash": code_hash(), "source": str(Path(source).resolve()),
              "historical_research": rules.get("historical_research", True),
              "registered_at": datetime.now(UTC).isoformat()}
    with (directory / "registration.json").open("x", encoding="utf-8") as stream:
        stream.write(canonical(record) + "\n")
    return record


def verify(directory, source):
    record = json.loads((Path(directory) / "registration.json").read_text(encoding="utf-8"))
    if (record["rules_hash"] != digest(record["rules"]) or record["data_hash"] != file_hash(source)
            or record["code_hash"] != code_hash()):
        raise ValueError("registration fingerprint changed; create a new study")
    return record


def read_attempts(path):
    path = Path(path)
    if not path.exists():
        return []
    records, previous = [], "0" * 64
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        checksum = row.pop("checksum")
        if row.get("previous") != previous or digest(row) != checksum:
            raise ValueError("ledger chain is invalid")
        row["checksum"] = checksum
        records.append(row)
        previous = checksum
    return records


def append_attempt(path, attempt):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        records = read_attempts(path)
        row = {**attempt, "time": datetime.now(UTC).isoformat(),
               "previous": records[-1]["checksum"] if records else "0" * 64}
        row["checksum"] = digest(row)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(canonical(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return row
    finally:
        os.close(descriptor)
        lock.unlink()


def check_evaluation(registration, today=None):
    today = datetime.now(ZoneInfo("Asia/Taipei")).date() if today is None else today
    rules = registration["rules"]
    earliest = datetime.fromisoformat(rules["earliest_evaluation"]).date()
    if today < earliest or today <= datetime.fromisoformat(rules["evaluation"][1]).date():
        raise ValueError("too early to evaluate")


def save_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")