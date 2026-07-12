#!/usr/bin/env python3
"""
核心 collection JSON Schema 驗證（P3 · 治本）。
把「隱性 schema 契約」變顯性——用 MongoDB $jsonSchema 驗證器，讓寫入不符結構時被記錄。

採 validationLevel='moderate' + validationAction='warn'：
  - warn = 只在 mongod log 記錄違規，**不拒絕寫入**（避免打斷日常 pipeline）。
  - moderate = 只驗新寫入與「原本就符合」的文件更新（不追溯既有不符文件）。
這是最安全的導入方式：先觀察違規、確認乾淨後再考慮升級 error。

用法:
  apply_schema_validation.py            列出將套用的驗證器（dry-run）
  apply_schema_validation.py --apply    實際套用
  apply_schema_validation.py --status   查看各表目前驗證器狀態
"""
import argparse
import sys

from pymongo import MongoClient

# 各核心表的驗證器（required + 關鍵欄位型別）。Decimal128 → bsonType 'decimal'。
VALIDATORS = {
    "stock_price": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["stock_id", "symbol", "date", "close"],
            "properties": {
                "stock_id": {"bsonType": "string"},
                "symbol": {"bsonType": "string"},
                "date": {"bsonType": "date"},
                "close": {"bsonType": ["decimal", "double", "int", "long"]},
            },
        }
    },
    "stock_factors": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "date"],
            "properties": {
                "symbol": {"bsonType": "string"},
                "date": {"bsonType": "date"},
            },
        }
    },
    "quarterly_earnings": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "year", "season"],
            "properties": {
                "symbol": {"bsonType": "string"},
                "year": {"bsonType": ["int", "long"]},
                "season": {"bsonType": ["int", "long"]},
            },
        }
    },
    "institutional_flow": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["stock_id", "date"],
            "properties": {
                "stock_id": {"bsonType": "string"},
                "date": {"bsonType": "date"},
            },
        }
    },
    "team_analysis": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["symbol", "date"],
            "properties": {
                "symbol": {"bsonType": "string"},
                "date": {"bsonType": "date"},
            },
        }
    },
}


def apply(db, coll, validator):
    db.command("collMod", coll, validator=validator,
               validationLevel="moderate", validationAction="warn")


def count_violations(db, coll, validator):
    """既有文件中不符驗證器的筆數（$nor + $jsonSchema）。"""
    try:
        return db[coll].count_documents({"$nor": [validator]})
    except Exception as e:
        return f"查詢失敗:{e}"


def main():
    ap = argparse.ArgumentParser(description="核心表 JSON Schema 驗證")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]

    if args.status:
        for coll in VALIDATORS:
            opts = db.command("listCollections", filter={"name": coll})["cursor"]["firstBatch"]
            v = opts[0].get("options", {}) if opts else {}
            has = "validator" in v
            print(f"{coll:22} 驗證器: {'已設定 (' + v.get('validationAction', '?') + ')' if has else '無'}")
        return

    for coll, validator in VALIDATORS.items():
        viol = count_violations(db, coll, validator)
        if args.apply:
            apply(db, coll, validator)
            print(f"✅ {coll:22} 已套用（warn/moderate）；既有不符文件: {viol}")
        else:
            req = validator["$jsonSchema"]["required"]
            print(f"{coll:22} required={req}  既有不符文件: {viol}")

    if not args.apply:
        print("\n[DRY-RUN] 未套用。加 --apply 執行（warn 模式，不會拒絕寫入）。")


if __name__ == "__main__":
    main()
