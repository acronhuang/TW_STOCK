"""TDD: LLM 只負責敘述——答案中的數字必須能在程式帶入的資料裡找到。"""

import pytest

from src.analysis.answer_guard import unsupported_numbers

pytestmark = pytest.mark.unit

CONTEXT = "2330 台積電 收盤2425.0(2026-10-09) PE28.1 近1年+93.5% 法人近10日淨: 外資+12,345張 合理價1084.96"


def test_numbers_that_appear_in_the_context_are_supported_whatever_the_formatting():
    answer = "收盤價 2,425 元，PE 28.1 倍，近一年漲 93.5%，外資買超 12345 張。"

    assert unsupported_numbers(answer, CONTEXT) == []


def test_a_number_the_context_never_gave_is_flagged():
    assert unsupported_numbers("目標價看到 3,000 元，PE 28.1。", CONTEXT) == ["3000"]


def test_each_unsupported_number_is_listed_once_in_order_of_appearance():
    assert unsupported_numbers("預估 3,000 元、再到 4,500 元，最後 3000 元。", CONTEXT) == ["3000", "4500"]


def test_rounding_an_integer_to_the_nearest_whole_number_is_allowed_but_not_a_wrong_decimal():
    assert unsupported_numbers("合理價約 1085 元", CONTEXT) == []
    assert unsupported_numbers("合理價 1084.5 元", CONTEXT) == ["1084.5"]


def test_dates_and_small_counts_are_not_treated_as_figures():
    assert unsupported_numbers("2026-10-09 當天共有 3 位委員、5 項理由，另 12/31 結算。", CONTEXT) == []


def test_percent_and_sign_are_normalised_before_comparison():
    assert unsupported_numbers("近一年 +93.5%", CONTEXT) == []
    assert unsupported_numbers("近一年 -93.5%", CONTEXT) == []   # 符號方向是另一個問題，這裡只核對數值是否出現


def test_an_answer_without_figures_has_nothing_to_flag():
    assert unsupported_numbers("資料庫中沒有相關內容。", CONTEXT) == []
