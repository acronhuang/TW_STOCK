Feature: 投資組合管理
  作為投資人
  我想要追蹤持股損益
  以便做出買賣決策

  Scenario: 買入登記
    Given 投組 "test" 為空
    When 我買入 "2330" 1000 股 @ 900 元
    Then 投組應有 1 支持股
    And "2330" 成本應為 900 元

  Scenario: 投組摘要
    Given 投組 "test" 有持股
    When 我查看投組摘要
    Then 應回傳 positions 清單
    And 每支持股有 avg_cost 和 shares

  Scenario: 多次加碼平均成本
    Given 投組 "test" 為空
    When 我買入 "1108" 1000 股 @ 14 元
    And 我再買入 "1108" 1000 股 @ 16 元
    Then "1108" 平均成本應為 15 元
    And 總股數應為 2000
