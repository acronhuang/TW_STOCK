Feature: 北大四大法則
  作為投資人
  我想要系統依照北大四大法則檢查我的持股
  以便即時發現風險

  Scenario: 法則一 — 334 倉位法
    Given 資金 400 萬
    When 市場週期為 "summer"
    Then 底倉建議 40%（160 萬）
    And 機動建議 30%（120 萬）
    And 現金保留 30%（120 萬）

  Scenario: 法則一 — 冬藏期空倉
    Given 資金 400 萬
    When 市場週期為 "winter"
    Then 現金保留 100%

  Scenario: 法則二 — 5% 無條件止損
    Given 持股成本 100 元
    When 現價跌到 94 元
    Then 行動應為 "止損出場"

  Scenario: 法則二 — 跌破 MA60 但獲利中
    Given 持股成本 20 元
    When 現價 22 元且跌破 60 日線
    Then 行動應為 "留意趨勢"（不是止損）

  Scenario: 法則三 — 買入三問
    Given 股票 RSI 為 75
    When 我執行買入三問
    Then Q3 空間應回傳 "超買" 且 pass=False

  Scenario: 主力洗盤偵測
    Given 近 5 日量比 > 1.5 且跌幅 > 3%
    When 我偵測主力階段
    Then 應判定為 "洗盤"
    And 建議 "不要賣，等洗盤結束"

  Scenario: 主力出貨偵測
    Given 近 5 日量比 > 2 且振幅 > 5%
    When 我偵測主力階段
    Then 應判定為 "出貨"
    And 建議 "獲利了結"
