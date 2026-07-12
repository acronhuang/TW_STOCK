Feature: 警報系統
  作為投資人
  我想要系統自動監控持股並發 LINE 通知
  以便不用盯盤

  Scenario: 價格跌破停損
    Given 持股 "7705" 停損價設為 33 元
    When 現價跌到 32.5 元
    Then 應觸發 LINE 通知
    And 通知內容包含 "停損" 和 "7705"

  Scenario: 價格達到目標
    Given 持股 "7705" 目標價設為 40 元
    When 現價漲到 40.5 元
    Then 應觸發 LINE 通知
    And 通知內容包含 "停利" 或 "目標"

  Scenario: 爆量警報
    Given 持股 "2603" 設爆量倍數 3x
    When 今日成交量為 20 日均量的 3.5 倍
    Then 應觸發爆量警報

  Scenario: 北大法則每日全檢
    When 排程執行 daily_alert_check
    Then 應檢查所有持股的 5% 止損線
    And 應檢查 MA60 位置
    And 應發送北大法則報告到 LINE
