Feature: 財報健康分析
  作為投資人
  我想要檢視個股財報健康狀況
  以便避開地雷股

  Scenario: 優質股票應為 A 級
    Given 股票 "2330" 台積電
    When 我執行財報健康分析
    Then 評級應包含 "A"
    And 獲利分數應 > 70

  Scenario: 杜邦分析
    Given 股票 "2330"
    When 我執行財報健康分析
    Then 應回傳杜邦拆解
    And ROE = 淨利率 × 週轉率 × 槓桿

  Scenario: 地雷股應有警示
    Given 股票 "7705" 三商餐飲（營收衰退）
    When 我執行財報健康分析
    Then 應有至少 1 條警示
    And 警示應包含 "衰退" 或 "偏弱"

  Scenario: 財報篩檢器
    Given 股票 "2330"
    When 我執行財報篩檢
    Then 應回傳 healthy=True

  Scenario: 虧損股應不健康
    Given 一支 4 季累計淨利為負的股票
    When 我執行財報篩檢
    Then 應回傳 healthy=False
