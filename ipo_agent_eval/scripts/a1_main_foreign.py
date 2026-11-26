"""Retrieve historical foreign-peer source material for the A1 blind packets."""

import hashlib
import json
import re
import subprocess
import unicodedata
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import cache
from pathlib import Path
from urllib.parse import urljoin

import fitz
import httpx
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parents[1] / "reports/a1_main/v1"
OUT = BASE / "c_source/foreign"
OUT.mkdir(parents=True, exist_ok=True)
AGENT = "IPO public disclosure research (academic source verification)"
US = {
    "CECO Environmental": ("20230925000332", "CECO", 3197),
    "Garmin Ltd": ("20250908000329", "GRMN", 1121788),
    "Motorola Solutions Inc": ("20250908000329", "MSI", 68505),
}
JAPAN = {
    "Keyence Corp": ("20241129001313", "6861", "E01967"),
    "NTT DATA Group": ("20241205000577", "9613", "E04911"),
    "Square Enix Holdings": ("20240520000263", "9684", "E04859"),
    "CYBERAGENT INC": ("20240520000263", "4751", "E05072"),
    "KADOKAWA CORP": ("20240520000263", "9468", "E30731"),
    "Shoei Co Ltd": ("20250908000329", "7839", "E02470"),
    "KOBELCO WIRE CO LTD": ("20250328002012", "5660", "E01282"),
    "NIPPON SEISEN CO LTD": ("20250328002012", "5659", "E01280"),
}


def fetch(ticker, key, url):
    path = OUT / ticker / key
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        response = httpx.get(
            url, headers={"User-Agent": AGENT}, timeout=22, follow_redirects=True
        )
        response.raise_for_status()
        path.write_bytes(response.content)
        path.with_name(path.name + ".url").write_text(
            str(response.url), encoding="utf8"
        )
    return path


def get_sec(name):
    case, ticker, cik = US[name]
    data = json.loads(
        fetch(
            ticker, "index.json", f"https://data.sec.gov/submissions/CIK{cik:010}.json"
        ).read_bytes()
    )
    rows = data["filings"]["recent"]
    valid = [
        i
        for i, form in enumerate(rows["form"])
        if form in {"10-Q", "10-K", "10-K/A", "10-Q/A"}
        and rows["filingDate"][i].replace("-", "") < case[:8]
    ]
    i = max(valid, key=lambda n: (rows["reportDate"][n], rows["filingDate"][n]))
    acc = rows["accessionNumber"][i]
    doc = rows["primaryDocument"][i]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
    meta = {
        "receipt": acc,
        "ticker": ticker,
        "published": rows["filingDate"][i].replace("-", ""),
        "period": rows["reportDate"][i],
        "title": rows["form"][i],
    }
    (OUT / ticker / "meta.json").write_text(json.dumps(meta), encoding="utf8")
    return fetch(ticker, "report.htm", url)


def get_japan(name):
    case, ticker, code = JAPAN[name]
    index = fetch(ticker, "list_irbank.htm", f"https://irbank.net/{code}/edinet")
    soup = BeautifulSoup(index.read_bytes(), "html.parser")
    choices = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 5:
            continue
        fy = re.search(r"(20\d\d)/(\d\d)", cells[0].get_text())
        if not fy or not int(case[:4]) - 2 <= int(fy[1]) <= int(case[:4]) + 1:
            continue
        for q, cell in enumerate(cells[1:], 1):
            a = cell.select_one('a[href^="notes?f=S100"]')
            if not a:
                continue
            doc = a["href"].split("=")[-1]
            md = a.get_text(strip=True).split("/")
            absolute_month = int(fy[1]) * 12 + int(fy[2]) - 1 - (4 - q) * 3
            yr, mo = divmod(absolute_month, 12)
            end = date(yr, mo + 1, monthrange(yr, mo + 1)[1])
            # The index gives month/day. Resolve fiscal-quarter boundary crossing,
            # then confirm the exact date on the actual regulator's cover page.
            filed = date(end.year, int(md[0]), int(md[1]))
            if filed < end:
                filed = filed.replace(year=filed.year + 1)
            if filed.strftime("%Y%m%d") < case[:8]:
                choices.append((filed.strftime("%Y%m%d"), doc, a["title"]))
    if not choices:
        raise ValueError(f"No statutory reports in index for {ticker}")
    published, doc, series = max(choices)
    url = f"https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/{doc}.pdf"
    path = fetch(ticker, doc + ".pdf", url)
    with fitz.open(path) as pdf:
        if not pdf.is_pdf:
            raise ValueError("Not EDINET PDF")
        first = pdf[0].get_text()
        if code not in first or not any(
            k in first for k in ("半期報告書", "四半期報告書", "有価証券報告書")
        ):
            raise ValueError(f"EDINET source identity mismatch: {ticker}")
        cover = unicodedata.normalize("NFKC", first)
        extracted = re.search(r"【提出日】\s*(20\d\d)年\s*(\d+)月\s*(\d+)日", cover)
        if (
            not extracted
            or date(*map(int, extracted.groups())).strftime("%Y%m%d") != published
        ):
            raise ValueError(f"EDINET cover disagrees with index: {ticker}")
        period = re.search(
            r"【(?:中間会計期間|四半期会計期間|事業年度)】\s*([^【]+)", cover
        )
    (OUT / ticker / "meta.json").write_text(
        json.dumps(
            {
                "ticker": ticker,
                "receipt": doc,
                "published": published,
                "title": series,
                "period": " ".join(period[1].split()) if period else series,
                "source": str(path.relative_to(BASE)),
                "publication_proof": "EDINET PDF physical page 1 提出日",
                "index": str(index.relative_to(BASE)),
            },
            ensure_ascii=False,
        ),
        encoding="utf8",
    )
    return path


def clean(value):
    return " ".join(value.split())


# Anchors refer only to frozen primary source paragraphs or rows in document order.
# Page 0 indicates the SEC's single HTML primary document. Bound the quote at a
# complete sentence or table-cell boundary before the 350-character packet limit.
JP_ROWS = {
    "6861": (
        (15, "当社グループは、電子応用機器", "省 略しております。"),
        (16, "当中間連結会計期間（自", "515,550"),
    ),
    "9613": (
        (3, "各事業の内容は以下のとおりです。", "提供する事業。"),
        (6, "当中間連結会計期間の業績は次のとおりです。", "7.8％増)となりました。"),
    ),
    "9684": (
        (3, "デジタルエンタテインメント事業、アミューズメント事業", "す。"),
        (3, "当事業における当第3四半期連結累計期間の売上高は", "2.6％減)"),
    ),
    "4751": (
        (3, "当社グループは、インターネット広告市場", "の投資を継続し、"),
        (3, "①メディア事業", "26.8％増）、"),
    ),
    "9468": (
        (
            2,
            "当第３四半期連結会計期間において、ゲームソフト開発等を行う",
            "含めております。",
        ),
        (3, "この結果、当事業の売上高は1,020億61百万円", "1.4％減）、"),
    ),
    "7839": (
        (3, "高級二輪乗車用ヘルメット市場は、", "状況にあります。"),
        (17, "当中間連結会計期間（自", "12,804,200"),
    ),
    "5660": (
        (3, "＜特殊鋼線関連事業＞", "(ばね・特殊線関連製品)"),
        (3, "その結果、特殊鋼線関連事業全体の販売数量は", "増収となり、"),
    ),
    "5659": (
        (3, "太陽光発電パネルなどの製造プロセスで使用される", "増益を確保しました。"),
        (
            3,
            "結果として、当中間連結会計期間におけるステンレス鋼線全体",
            "6.1％増）となりました。",
        ),
    ),
}
US_ROWS = {
    "CECO": (
        (
            0,
            "Wakefield is a producer of industrial engineered noise",
            "skid enclosures,",
        ),
        (
            0,
            "Three months ended June 30, Six months ended June 30, (in thousands) 2023 2022 2023 2022 Net sales (less",
            "73,503",
        ),
    ),
    "MSI": (
        (
            0,
            "Within these segments the Company has three principal product lines",
            "Command Center.",
        ),
        (
            0,
            "Three Months Ended Six Months Ended June 28, 2025 June 29, 2024 June 28, 2025 June 29, 2024 Net sales from products",
            "2,049",
        ),
    ),
    "GRMN": (
        (0, "Note 11 also contains disaggregated revenue information", "auto OEM."),
        (
            0,
            "Fitness Outdoor Aviation Marine Auto OEM Total 13-Weeks Ended June 28, 2025",
            "1,814,564",
        ),
    ),
}
NEUTRAL = {
    "ABEMA": "[서비스]",
    "WINTICKET": "[서비스]",
    "㈱アクワイア": "[기업]",
    "NASclean®": "[제품]",
    "Wakefield": "[자회사]",
}
TAIWAN = {
    "Eclat Textile Company": ("20240305000170", "1476"),
    "Makalot Industrial": ("20240305000170", "1477"),
    "Faraday Technology Corp": ("20230915000263", "3035"),
    "Global Unichip Corp": ("20230915000263", "3443"),
    "Alchip Technologies": ("20230915000263", "3661"),
}


@cache
def twse_address():
    host = "doc.twse.com.tw"
    ips = httpx.get(
        "https://dns.google/resolve", params={"name": host, "type": "A"}, timeout=15
    ).json()["Answer"]
    return next(ip["data"] for ip in ips if ip["type"] == 1)


def twse_http(url, args=()):
    host = "doc.twse.com.tw"
    # Preserve original HTTPS hostname, certificate verification and SNI when
    # the workstation's DNS fails on this particular official archive hostname.
    addr = twse_address()
    cmd = [
        "curl.exe",
        "-fsSL",
        "--max-time",
        "45",
        "--resolve",
        f"{host}:443:{addr}",
        *args,
        url,
    ]
    last = None
    for _ in range(3):
        last = subprocess.run(cmd, capture_output=True, check=False)
        if not last.returncode:
            return last.stdout
    raise ValueError("TWSE download failed: " + str(last.returncode))


def tw_report(name):
    case, t = TAIWAN[name]
    ep = "https://doc.twse.com.tw/server-java/t57sb01"
    idx = OUT / t / "mops_timestamps.htm"
    idx.parent.mkdir(parents=True, exist_ok=True)
    if not idx.exists():
        u = ep + "?step=1&colorchg=1&co_id=" + t + "&year=112&seamon=&mtype=A"
        idx.write_bytes(twse_http(u))
        idx.with_name(idx.name + ".url").write_text(u, encoding="utf8")
    soup = BeautifulSoup(idx.read_bytes().decode("cp950", "replace"), "html.parser")
    eligible = []
    for tr in soup.select("tr"):
        text = clean(tr.get_text(" ", strip=True))
        m = re.search(
            r"(2023(0[1-4])_"
            + t
            + r"_AI1\.pdf) ([\d,]+) (\d+)/(\d+)/(\d+) (\d\d:\d\d:\d\d)",
            text,
        )
        if m:
            filename, q, size, y, mo, d, tim = m.groups()
            day = f"{int(y) + 1911:04}{int(mo):02}{int(d):02}"
            if day < case[:8]:
                eligible.append((q, day, filename, int(size.replace(",", "")), tim))
    q, day, filename, size, tim = max(eligible)
    path = OUT / t / filename
    u = ep + "?step=9&kind=A&co_id=" + t + "&filename=" + filename
    if (
        not path.exists()
        or path.stat().st_size != size
        or b"%%EOF" not in path.read_bytes()[-1500:]
    ):
        href = BeautifulSoup(twse_http(u), "html.parser").select_one("a[href*='.pdf']")[
            "href"
        ]

        def part(start):
            end = min(size, start + 98304) - 1
            raw = twse_http(urljoin(ep, href), ["-D", "-", "-r", f"{start}-{end}"])
            h, body = raw.split(b"\r\n\r\n", 1)
            if (
                f"content-range: bytes {start}-{end}/{size}".encode() not in h.lower()
                or len(body) != end - start + 1
            ):
                raise ValueError("TWSE Content-Range or size mismatch")
            return body

        with ThreadPoolExecutor(max_workers=5) as pool:
            doc = b"".join(pool.map(part, range(0, size, 98304)))
        if (
            len(doc) != size
            or not doc.startswith(b"%PDF")
            or b"%%EOF" not in doc[-1500:]
        ):
            raise ValueError("TWSE incomplete PDF archive")
        path.write_bytes(doc)
        path.with_name(path.name + ".url").write_text(u, encoding="utf8")
    return path, {
        "ticker": t,
        "receipt": filename,
        "published": day,
        "published_local_time": tim + " +08:00",
        "period": "2023Q" + str(int(q)),
        "title": f"{t} 2023Q{int(q)} IFRSs consolidated financial statements",
        "index": idx.relative_to(BASE).as_posix(),
        "publication_proof": "TWSE original Chinese financial statement upload timestamp",
    }


def clip(path, document, page, start, end, section=None):
    where = document.find(start)
    stop = document.find(end, where + len(start))
    if where < 0 or stop < 0:
        raise ValueError(f"Inspect anchor: {path.parent.name}, {page}, {start}, {end}")
    quote = document[where : stop + len(end)]
    text = quote
    for word, alias in NEUTRAL.items():
        text = text.replace(word, alias)
    if len(text) > 350:
        raise ValueError(f"Excerpt exceeds 350 characters: {path.parent.name}, {page}")
    return {
        "quote": quote,
        "text": text,
        "url": path.with_name(path.name + ".url").read_text(encoding="utf8"),
        "snapshot": path.relative_to(BASE).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "location": section
        or (
            f"PDF physical page {page}, normalized text offset {where}"
            if page
            else f"Primary HTML visible text, normalized offset {where}"
        ),
    }


def export_jp_us(name):
    case, ticker, _ = (US | JAPAN)[name]
    if name in US:
        path = get_sec(name)
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        for el in soup.find_all(["ix:header", "script", "style"]):
            el.decompose()
        doc = {0: clean(soup.get_text(" ", strip=True))}
        anchor = US_ROWS[ticker]
    else:
        path = get_japan(name)
        with fitz.open(path) as pdf:
            doc = {i + 1: clean(p.get_text()) for i, p in enumerate(pdf)}
        anchor = JP_ROWS[ticker]
    result = json.loads((OUT / ticker / "meta.json").read_bytes())
    if name in US:
        result.update(
            index=(OUT / ticker / "index.json").relative_to(BASE).as_posix(),
            publication_proof="SEC submissions filingDate, accession number, and primaryDocument",
        )
    for attr, (page, start, end) in zip(["business", "financials"], anchor):
        result[attr] = [clip(path, doc[page], page, start, end)]
    product_detail = {
        "GRMN": (
            "The increase in fitness revenue was driven by strong demand for advanced wearables.",
            "sales growth in adventure watches.",
        ),
        "MSI": (
            "LMR Communications: Infrastructure, devices",
            "to assure availability, security and resiliency.",
        ),
    }
    if ticker in product_detail:
        # Retain the first category paragraph and the first description of products.
        result["business"].append(clip(path, doc[0], 0, *product_detail[ticker]))
    if ticker in {"9468", "9684"}:
        start, end = (
            ("［出版事業］ 出版事業では、", "ります。")
            if ticker == "9468"
            else (
                "①デジタルエンタテインメント事業 ゲームを中心とする",
                "行っております。",
            )
        )
        result["business"].append(clip(path, doc[3], 3, start, end))
    if ticker == "9613":
        result["financials"] = [
            clip(
                path,
                doc[6],
                6,
                "（日本） 各分野とも、",
                "886,628百万円(前年同期比7.8％増)となりました。",
            )
        ]
    if ticker in {"9684", "9468"}:
        start, end, segment = {
            "9684": (
                "当第3四半期連結累計期間の業績は、売上高は",
                "0.8％増)",
                "①デジタルエンタテインメント事業",
            ),
            "9468": (
                "当第３四半期連結累計期間における業績は、売上高",
                "1.4％減）",
                "［出版事業］",
            ),
        }[ticker]
        result["financials"][0]["location"] += ", section " + segment
        result["financials"][0]["section_heading_quote"] = segment
        result["financials"].insert(0, clip(path, doc[3], 3, start, end))
    if name in JAPAN:
        # The quarter on an EDINET cover can differ from the cumulative period of
        # its segment revenue. Page 2 lists prior YTD, current YTD, then prior FY.
        periods = list(
            re.finditer(
                r"自\s*(\d{4})年\s*(\d+)月(\d+)日\s*至\s*(\d{4})年\s*(\d+)月(\d+)日",
                doc[2],
            )
        )
        if (
            len(periods) < 3
            or "売上高" not in doc[2][periods[2].end() : periods[2].end() + 55]
        ):
            raise ValueError("Unexpected EDINET cumulative period header " + ticker)
        dates = tuple(map(int, periods[1].groups()))
        first, last = date(*dates[:3]), date(*dates[3:])
        label = f"{first.isoformat()}~{last.isoformat()} 연결 누계"
        proof = {
            "location": "PDF physical page 2, current-period management indicators",
            "quote": periods[1][0],
        }
    else:
        label = {
            "GRMN": "2025-06-28 종료 13주",
            "CECO": "2023·2022년 6월 30일 종료 3개월·6개월",
            "MSI": "2025-06-28·2024-06-29 종료 3개월·6개월",
        }[ticker]
        proof = {
            "location": result["financials"][0]["location"],
            "quote": result["financials"][0]["quote"],
        }
    for row in result["financials"]:
        row.update(period=label, period_proof=proof)
    return case, result


TW_ROWS = {
    "1476": (
        (11, "本公司及子公司(以下併稱", "加工買賣為主。"),
        (37, "(十七)客戶合約之收入", "17,296,359"),
    ),
    "1477": (
        (9, "主要營業項目為從事", "加工等業務。"),
        (23, "收入之細分 112年7月至9月", "9,272,068"),
    ),
    "3035": (
        (10, "主要營業項目 為研究", "(ASIC EDA Tools)。"),
        (24, "(1) 收入細分", "610,038"),
    ),
    "3443": (
        (9, "主要營業項目為研究", "相關業務。"),
        (31, "營業收入 本公司所產生", "3,050,359"),
    ),
    "3661": (
        (17, "主要經營研究開發", "相關服務等。"),
        (38, "客戶合約收入之細分", "99,090"),
    ),
}


def export_tw(name):
    case, t = TAIWAN[name]
    path, meta = tw_report(name)
    with fitz.open(path) as pdf:
        if pdf.is_repaired or not len(pdf):
            raise ValueError("TWSE incomplete report")
        for field, (page, start, end) in zip(("business", "financials"), TW_ROWS[t]):
            meta[field] = [
                clip(path, clean(pdf[page - 1].get_text()), page, start, end)
            ]
    period = {"1476": "2023·2022 회계연도", "1477": "2023년 7~9월"}.get(
        t
    ) or "2023·2022년 4~6월 및 1~6월"
    for row in meta["financials"]:
        row.update(
            period=period,
            period_proof={"quote": row["quote"], "location": row["location"]},
        )
    return case, meta


if __name__ == "__main__":

    def process(name):
        try:
            return name, export_tw(name) if name in TAIWAN else export_jp_us(name)
        except (ValueError, KeyError, OSError, httpx.HTTPError, RuntimeError) as exc:
            case, ticker, *_ = (US | JAPAN | TAIWAN)[name]
            return name, (
                case,
                {"ticker": ticker, "business": [], "financials": [], "issue": str(exc)},
            )

    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for name, (case, record) in pool.map(process, [*US, *JAPAN, *TAIWAN]):
            results.setdefault(case, {})[name] = record
            print(name, record.get("issue", "verified"), flush=True)
    (OUT.parent / "foreign.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
