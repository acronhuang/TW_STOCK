#!/bin/bash
cd /home/mdsadmin/Stock/tw-stock-analysis
PY=/home/mdsadmin/Stock/.venv/bin/python
LOG=/tmp/robustness_summary.log
: > $LOG
run(){ # preset start end qsrc tag
  echo ">>> $5" >> $LOG
  $PY scripts/robustness_value.py --preset "$1" --start-date "$2" --end-date "$3" --quality-source "$4" --output "results_rob_$5.json" 2>/dev/null | grep -E "RESULT|PRESET" >> $LOG
}
run value_only    2022-01-01 2024-12-31 none        val_2022_2024
run value_only    2024-01-01 2026-06-30 none        val_2024_2026
run value_only    2022-01-01 2026-06-30 none        val_full
run momentum_only 2022-01-01 2024-12-31 none        mom_2022_2024
run full          2024-01-01 2026-06-30 none        full_2024_2026
run full          2022-01-01 2024-12-31 fundamental fullQ_2022_2024
echo "ALL_DONE" >> $LOG
