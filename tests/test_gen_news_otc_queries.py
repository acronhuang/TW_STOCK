"""出題時只移除主旨開頭的公司名，不能誤刪主旨中間的新舊公司名。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from gen_news_otc_queries import clean_subject  # noqa: E402


def test_rename_notice_keeps_new_name():
    subject = "公告本公司名稱由「緯創軟體股份有限公司」更名為「緯致科技股份有限公司」"
    assert "緯致科技股份有限公司" in clean_subject(subject, "緯致*")


def test_leading_company_name_is_removed():
    assert clean_subject("德麥 公告取得結構性存款", "德麥") == "公告取得結構性存款"


def test_leading_full_name_removed_with_short_name():
    assert clean_subject("鈦昇科技股份有限公司公告董事會召開日期", "鈦昇科技股份有限公司") == "公告董事會召開日期"