"""TDD: 清除預設持有的修復腳本——dry-run 不寫入、apply 先備份、不動 updated_at。"""

import json
from datetime import datetime

import pytest

from scripts import clear_fallback_verdicts as module

pytestmark = pytest.mark.unit

SKIP = "整合略過：角色報告全數為錯誤訊息，不以此做決策"
NOW = datetime(2026, 10, 11, 12, 0)


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.updates = []

    def find(self, query, projection=None):
        return self.documents

    def update_many(self, query, update):
        self.updates.append((query, update))


def doc(identifier, verdict="持有", advisor=SKIP, n=0):
    return {"_id": identifier, "symbol": "2330", "date": datetime(2026, 9, 22), "final_verdict": verdict,
            "advisor": advisor, "consensus": {"n": n}, "updated_at": datetime(2026, 9, 22, 1, 0)}


def test_dry_run_reports_targets_and_writes_nothing(tmp_path):
    collection = Collection([doc("a"), doc("b", advisor="評級：賣出", verdict="賣出")])
    backup = tmp_path / "b.jsonl"

    targets = module.clear_fallback_verdicts(collection, backup, False, datetime(2026, 9, 1), NOW)

    assert [t["_id"] for t in targets] == ["a"]
    assert collection.updates == [] and not backup.exists()


def test_apply_backs_up_the_original_verdict_then_clears_only_the_verdict(tmp_path):
    collection = Collection([doc("a")])
    backup = tmp_path / "sub" / "b.jsonl"

    module.clear_fallback_verdicts(collection, backup, True, datetime(2026, 9, 1), NOW)

    saved = [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()]
    assert saved[0]["final_verdict"] == "持有" and saved[0]["_id"] == "a"
    query, update = collection.updates[0]
    assert update["$set"]["final_verdict"] is None and "updated_at" not in update["$set"]
    assert update["$set"]["ollama_failed"] is True


def test_nothing_to_clear_writes_no_backup(tmp_path):
    backup = tmp_path / "b.jsonl"

    module.clear_fallback_verdicts(Collection([doc("a", n=3, advisor="評級：買進")]), backup, True, datetime(2026, 9, 1), NOW)

    assert not backup.exists()
