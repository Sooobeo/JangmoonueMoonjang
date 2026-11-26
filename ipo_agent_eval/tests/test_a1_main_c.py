from bs4 import BeautifulSoup

from scripts.main_c_prepare import business_excerpt, mask


def test_company_product_data_in_first_tbody_row_is_eligible():
    doc=BeautifulSoup(
        "<table><thead><tr><th>사업부문</th><th>주요제품</th></tr></thead>"
        "<tbody><tr><td>전력산업</td><td>배전용 전선퓨즈</td></tr></tbody></table>", "lxml")
    row=doc.select_one("tbody tr")
    assert business_excerpt(row.get_text(" ",strip=True),row,"사업부문 주요제품",{"name":"보성파워텍"})
    header=doc.select_one("thead tr")
    assert not business_excerpt(header.get_text(" ",strip=True),header,"사업부문 주요제품",{"name":"보성파워텍"})


def test_neutral_mask_preserves_product_descriptions_and_masks_direct_names():
    fact={"quote":"애플리케이션과 홈 뷰티 디바이스를 제공하는 Fasoo와 애플","field":"business"}
    value,changes=mask(fact,[])
    assert value=="애플리케이션과 홈 뷰티 디바이스를 제공하는 [기업]와 [기업]"
    assert set(changes)=={"Fasoo","애플"}


def test_financial_excerpt_preserves_report_period_and_section_label():
    fact={"quote":"売上高123億円","field":"financials","period":"2024.03","section_heading_quote":"出版事業"}
    value,_=mask(fact,[])
    assert "2024.03" in value and "出版事業" in value and "123億円" in value
