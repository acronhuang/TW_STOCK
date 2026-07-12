Feature: 股票綜合排行
  作為投資人
  我想要看到全市場股票排行
  以便找到值得投資的標的

  Background:
    Given MongoDB 資料庫已連線
    And stock_factors 有最近 7 天的資料

  Scenario: 基本排行產出
    When 我執行綜合排行 limit 10
    Then 應回傳 10 支股票
    And 每支都有 total_score 欄位
    And 排行依 total_score 遞減排序

  Scenario: 財報篩檢過濾地雷股
    When 我執行綜合排行 financial_check=True
    Then 回傳的股票都應通過財報健康檢查
    And 不應包含 4 季累計淨利為負的股票

  Scenario: PE 範圍過濾
    When 我執行綜合排行 min_pe=5 max_pe=20
    Then 回傳的股票 PE 都在 5-20 之間
