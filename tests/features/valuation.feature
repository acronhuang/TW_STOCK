Feature: 估值分析
  作為投資人
  我想要知道個股的合理價
  以便判斷是否值得買入

  Scenario: DCF 估值
    Given 股票 "2330" 有近 4 季營運資料
    When 我執行 DCF 估值
    Then 應回傳 fair_value 大於 0
    And WACC 應不低於 8%

  Scenario: DDM 估值
    Given 股票 "2892" 有股利歷史
    When 我執行 DDM 估值
    Then 應回傳 fair_value 大於 0
    And 股利成長率應不超過 5%

  Scenario: PE Band 估值
    Given 股票 "1229" 有近 3 年 PE 歷史
    When 我執行 PE Band 估值
    Then PE 中位數應不超過 25 倍
    And 應回傳 zone（便宜/合理/昂貴）

  Scenario: TTM EPS 正確計算
    Given 股票 "2706" 近 4 季 EPS 為 0.12, 0.20, 0.24, 0.65
    When 我計算 TTM EPS
    Then 結果應為 1.21（直接加總，不誤判 Q4 為累計）

  Scenario: 無資料時不編造數字
    Given 股票 "9999" 不存在
    When 我執行估值分析
    Then 應回傳 error 而非虛構合理價
