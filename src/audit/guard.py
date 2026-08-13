"""稽核護欄:強制「已知答案對照組」,且驗證對照組本身的涵蓋完整性。

═══════════════════════════════════════════════════════════════════════
為什麼需要這個模組(2026-08-13)

    一晚之內同類錯誤犯了 9 次,共同病因是:**用未經驗證的代理指標推論全域
    結論**。錯誤的結果看起來完全正常 —— 不拋例外、格式正確、數值合理,
    只有拿已知答案去對才會現形。四種變形:

      取樣偏誤   `sort("_id",-1)` 取到最新寫入批次 → 把 388 萬筆非空的
                 pe_ratio 報成「不存在」
      讀錯來源   從 `_fundamental_quality()` 回傳讀 available_from,
                 但它不回傳該欄 → 每筆都是 None → 全標「前視」
      定義不一致 沒套用生產程式自身的股票池定義 → 落後檔數 607 vs 實際 159
      只看儲存層 見最新日 pe 只有 630 筆就下結論,實際取用端有 30 天回退

    當晚**唯二沒出錯**的檢查,共同點都是帶「已知答案」的 sanity_check
    —— 其中一支還兩度攔下會靜默寫壞資料的口徑陷阱。

🔴 但光有對照組不夠。field_contract_audit 第二版**有**對照組,卻只涵蓋
   stock_factors;fundamental_factors 那條路徑沒被涵蓋,照樣輸出六個假警報。
   **對照組只保護到它涵蓋的範圍。**

   所以本模組的核心不是「跑對照組」,而是**驗證對照組的涵蓋完整性**:
   凡是被稽核到的資料來源,都必須有正向與反向對照;缺一個就拒絕執行。
   把「忘記加對照」從「安靜地產生假結論」變成「立刻拋錯」。
═══════════════════════════════════════════════════════════════════════

用法:

    from src.audit.guard import AuditGuard

    guard = AuditGuard("欄位契約稽核")
    guard.add_control("stock_factors", "return_6m", expect="OK")
    guard.add_control("stock_factors", "op_margin", expect="MISSING")
    guard.add_control("fundamental_factors", "roe", expect="OK")
    guard.add_control("fundamental_factors", "__nonexistent__", expect="MISSING")

    guard.verify(measure_fn)        # 對照不過 → SystemExit,不輸出任何結論
    ...
    guard.audited("stock_factors")  # 每稽核一個來源就登記
    guard.finish()                  # 有登記但沒對照的來源 → 拋錯
"""
from datetime import datetime


class ControlFailed(RuntimeError):
    """對照組未通過 —— 本次量測方法不可信。"""


class ControlCoverageGap(RuntimeError):
    """有資料來源被稽核卻沒有對照組 —— 正是 2026-08-13 踩過的坑。"""


class AuditGuard:
    def __init__(self, name, require_both_directions=True):
        self.name = name
        self.controls = []            # [(source, key, expect)]
        self._audited = set()         # 實際被稽核到的來源
        self._verified = False
        self.require_both = require_both_directions

    # ── 宣告階段 ────────────────────────────────────────────────────
    def add_control(self, source, key, expect):
        """登記一組對照。expect 是這支稽核自己的判定值(如 "OK"/"MISSING")。

        正向對照(已知該有)被判成「沒有」→ 量測方法壞了。
        反向對照(已知沒有)被判成「有」→ 判定邏輯失效。
        兩個方向都要,只有正向會漏掉「什麼都判成 OK」的退化。
        """
        self.controls.append((source, key, expect))

    def audited(self, source):
        """登記「我稽核了這個來源」。finish() 會據此檢查對照涵蓋。"""
        self._audited.add(source)

    # ── 執行階段 ────────────────────────────────────────────────────
    def verify(self, measure, on_fail=None):
        """跑所有對照。measure(source, key) → 判定值。

        任一組不符即中止 —— **不要改成「印警告後照跑」**,那等於又產出
        一份看起來正常的假結論,正是本模組要根除的東西。
        """
        if not self.controls:
            raise ControlCoverageGap(
                f"[{self.name}] 沒有任何對照組。稽核必須先證明自己的量測方法可信,"
                f"否則結論無法與『看起來正常的錯誤』區分。")

        print(f"對照組({self.name}) —— 不通過即中止,不輸出任何結論:")
        failed = []
        for source, key, expect in self.controls:
            got = measure(source, key)
            ok = (got == expect)
            print(f"  {'✅' if ok else '🔴'} {source}.{key:<20} "
                  f"期望 {expect:<8} 實得 {got}")
            if not ok:
                failed.append((source, key, expect, got))

        if failed:
            print(f"\n🔴 對照組未通過({len(failed)} 組)—— 量測或判定邏輯有問題。")
            print("   本次不輸出任何結論。修好量測方法再跑,不要繞過這道檢查。")
            if on_fail:
                on_fail(failed)
            raise SystemExit(1)

        self._verified = True
        return True

    def finish(self):
        """收尾:檢查每個被稽核的來源都有(雙向)對照。

        這是本模組真正的價值 —— 2026-08-13 的失敗不是「沒有對照組」,
        而是「對照組漏了一個來源」,而那條路徑就安靜地吐出假警報。
        """
        if not self._verified:
            raise ControlFailed(
                f"[{self.name}] 尚未執行 verify() 就想收尾。對照組是前置條件,不是裝飾。")

        by_source = {}
        for source, _, expect in self.controls:
            by_source.setdefault(source, set()).add(expect)

        problems = []
        for source in sorted(self._audited):
            if source not in by_source:
                problems.append(f"{source}:被稽核卻**完全沒有**對照組")
            elif self.require_both and len(by_source[source]) < 2:
                only = ", ".join(sorted(by_source[source]))
                problems.append(f"{source}:只有單向對照({only}),"
                                f"無法偵測『全部判成同一值』的退化")
        if problems:
            msg = (f"[{self.name}] 對照組涵蓋不完整,結論不可信:\n  - "
                   + "\n  - ".join(problems)
                   + "\n\n  對照組只保護到它涵蓋的範圍。請為每個資料來源各補上"
                     "正向與反向對照後再跑。")
            raise ControlCoverageGap(msg)

        print(f"\n✅ 對照涵蓋完整:{len(self._audited)} 個來源皆有雙向對照 "
              f"({datetime.now():%H:%M:%S})")


def cross_check(name, method_a, method_b, tol=0.0):
    """同一個數字用兩種結構不同的方法各算一次,不一致即拋錯。

    用於「沒有已知答案可對」的情況 —— 兩個獨立方法同時錯成一樣的機率遠低於
    單一方法出錯。2026-08-13 的 MOPS 補洞就是靠這招驗收:寫入值 vs 從另一端
    重新差分,五筆逐一比對到個位數。
    """
    a, b = method_a(), method_b()
    if a is None or b is None:
        raise ControlFailed(f"[{name}] 有一方算不出來:a={a} b={b}")
    diff = abs(a - b)
    if diff > tol:
        raise ControlFailed(
            f"[{name}] 兩種方法不一致:{a} vs {b}(差 {diff},容忍 {tol})。"
            f"兩者結構不同卻應等價 —— 至少一邊有錯,不要挑順眼的用。")
    return a
