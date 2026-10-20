#!/usr/bin/env python3
"""每 2 分鐘取樣兩台推理節點的 GPU 使用率與顯存，附加到 logs/gpu_util.csv；scripts/gpu_report.py 依 4 小時分組。

取樣失敗（SSH 不通、nvidia-smi 回錯誤）也會留一列空值，報表才看得到缺口，而不是悄悄少一段。
每台節點只有一張 GPU，只讀 nvidia-smi 的第一列。
"""
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.moe import model_nodes  # noqa: E402

OUT = ROOT / "logs" / "gpu_util.csv"
HEADER = ["time", "node", "util_pct", "mem_used_mib", "mem_total_mib", "temp_c"]
QUERY = "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"


def nodes():
    return {"28": urlparse(model_nodes.NODE_28).hostname, "27": urlparse(model_nodes.NODE_27).hostname}


def parse(text):
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            return [int(p) for p in parts]
    return None


def sample(host, run=subprocess.run):
    try:
        result = run(["ssh", "-n", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, QUERY],
                     capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return None
    return parse(result.stdout)


def main(out=OUT, now=datetime.now, run=subprocess.run):
    out.parent.mkdir(parents=True, exist_ok=True)
    fresh = not out.exists() or out.stat().st_size == 0
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if fresh:
            writer.writerow(HEADER)
        for node, host in nodes().items():
            values = sample(host, run)
            writer.writerow([stamp, node, *(values or ["", "", "", ""])])
            if values is None:
                print(f"{stamp} .{node} 取樣失敗", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
