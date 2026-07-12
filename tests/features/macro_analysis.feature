Feature: 總經分析
  作為投資人
  我想要了解大盤環境
  以便決定倉位水位

  Scenario: 總經評分
    When 我查詢總經訊號
    Then 應回傳 score（-100 到 +100）
    And 應回傳 verdict（偏多/偏空/中性）

  Scenario: 市場週期判斷
    When 我查詢市場週期
    Then 應回傳 cycle（spring/summer/autumn/winter）
    And 應回傳建議倉位比例

  Scenario: 外資動向
    When 我查詢總經概覽
    Then 應包含 foreign_net_5d（外資近 5 日買賣超）
    And 應包含 etf_0050 價格
