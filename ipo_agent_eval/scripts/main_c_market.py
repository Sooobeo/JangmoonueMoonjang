"""Archive KIND's historical membership and intervening industry-change notices."""
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Event

import httpx
from bs4 import BeautifulSoup

from scripts.main_c_reports import SOURCE, ROSTER, dump, read, digest, clean

KIND = "https://kind.krx.co.kr"
DETAILS = KIND + "/disclosure/details.do"
LISTING = KIND + "/corpgeneral/listedissuestatusdetail.do"
EXCHANGE_UNAVAILABLE = Event()
SNAPSHOTS = {
    "20221126191832": "&searchType=13&", "20240217134436": "&searchType=13",
    "20240512053202": "", "20240911062238": "&searchType=13", "20250324030950": "&searchType=13",
    "20250617131529": "", "20250913152309": "", "20251112194108": "",
}


def html(blob):
    return BeautifulSoup(blob, "lxml")


def fetch(path, url, params=None, post=False):
    if path.exists():
        saved=path.read_bytes()
        if "비정상 대량".encode() in saved or "비정상 대량".encode("cp949") in saved:
            raise RuntimeError("Stored file is an access restriction notice")
        return saved
    if EXCHANGE_UNAVAILABLE.is_set():
        raise RuntimeError("Exchange access is restricted")
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        for attempt in range(4):
            try:
                if post:
                    r = c.post(url, data=params, headers={"Referer": DETAILS + "?method=searchDetailsMain",
                                                         "X-Requested-With": "XMLHttpRequest"})
                else:
                    r = c.get(url, params=params)
                r.raise_for_status()
                visible=r.content.decode("utf8",errors="ignore")+r.content.decode("cp949",errors="ignore")
                if "접속이 일시적으로 제한" in visible or "비정상 대량" in visible:
                    EXCHANGE_UNAVAILABLE.set()
                    raise RuntimeError("Exchange returned an access restriction; collection stopped")
                if len(r.content) < 800 or "서비스 이용에 불편".encode() in r.content:
                    raise ValueError("Invalid KIND document")
                break
            except (httpx.HTTPError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def archives():
    for ts, suffix in SNAPSHOTS.items():
        url = ("https://web.archive.org/web/" + ts +
               "id_/https://kind.krx.co.kr/corpgeneral/corpList.do?method=download" + suffix)
        path = SOURCE / "kind" / (ts + ".html")
        fetch(path, url)
        path.with_suffix(".url").write_text(url, encoding="utf8")


def corp_rows(blob):
    rows = html(blob).select("table tr")
    fields = [v.get_text(strip=True) for v in rows[0].select("th")]
    out = []
    for row in rows[1:]:
        x = dict(zip(fields, [e.get_text(strip=True) for e in row.select("td")]))
        if re.fullmatch(r"[A-Z0-9]{6}", x.get("종목코드", "")):
            out.append(x)
    return out


def market(task):
    cutoff, mkt = task
    folder = SOURCE / "membership" / cutoff
    day = date.fromisoformat(cutoff) - timedelta(days=1)
    for delta in range(8):
        asof = day - timedelta(days=delta)
        p = dict(method="searchListedIssueStatDetailSub", forward="listedissuestatdetail_down",
                 currentPageSize="3000", pageIndex="1", mktId=mkt, secugrpId="ST",
                 detailType="1", selDate=asof.strftime("%Y%m%d"))
        path = folder / (mkt + "-" + p["selDate"] + ".html")
        blob = fetch(path, LISTING, p, True)
        rows = corp_rows(blob)
        if len(rows) > 400:
            dump(folder / (mkt + ".json"), {"url": LISTING, "params": p, "as_of": str(asof),
                 "sha256": digest(blob), "snapshot": path.relative_to(SOURCE.parent).as_posix(),
                 # KIND may display a later corporate name or transferred listing day.
                 # Market membership is the actual historical result of the market-specific query.
                 "rows": [{"ticker": r["종목코드"], "name": r["회사명"]} for r in rows]})
            return
    raise ValueError(f"No market membership for {cutoff}/{mkt}")


def changes(start, end):
    folder = SOURCE / "kind_changes"
    form = html(fetch(folder/"form.html", DETAILS, {"method":"searchDetailsMain"})).select_one("form#searchForm")
    p = {o["name"]:o.get("value","") for o in form.select("input[name]")
         if o.get("type") not in ("checkbox","radio") or o.has_attr("checked")}
    p.update(method="searchDetailsSub", forward="details_sub", reportNm="업종변경", reportNmTemp="업종변경",
             fromDate=start, toDate=end, currentPageSize="100", pageIndex="1")
    rows, total = [], None
    for page in range(1,50):
        p["pageIndex"] = str(page)
        path = folder / f"{start}-{end}-{page}.html"
        doc = html(fetch(path, DETAILS, p, True))
        page_rows = []
        for tr in doc.select("tbody tr"):
            a = tr.select_one('a[onclick*="openDisclsViewer"]')
            firm = tr.select_one('a[onclick*="companysummary"]')
            if a and firm:
                k = re.search(r"'([A-Z0-9]+)'", firm["onclick"])[1]
                # KIND internal firm identifier is *not* a ticker. Resolve by name
                # and keep the raw identifier for corporations that changed names.
                page_rows.append({"name": firm.get_text(strip=True), "firm_id": k, "published":
                        tr.select("td")[1].get_text(strip=True), "market": tr.select("td")[2].img["alt"],
                        "receipt": re.search(r"'(\d{14})'", a["onclick"])[1], "title": a["title"]})
        if total is None:
            total = int(doc.select_one("tbody tr td").get_text(strip=True)) if page_rows else 0
        rows.extend(page_rows)
        if len(rows) >= total:
            break
        if not page_rows:
            raise ValueError("Pagination incomplete")
    if len({r["receipt"] for r in rows}) != total:
        raise ValueError("Duplicate/missing exchange notices")
    dump(folder/(start + ".json"), {"term":"업종변경", "from":start, "to":end, "rows":rows})
    return rows


def notice(r):
    folder = SOURCE/"kind_changes"/r["receipt"]
    url = KIND + "/common/disclsviewer.do"
    cover = html(fetch(folder/"cover.html", url, {"method":"search","acptno":r["receipt"]}))
    sel = cover.select_one("option[selected][value*='|']")
    if not sel:
        return
    docno = sel["value"].split("|")[0]
    frame = fetch(folder/"frame.html", url, {"method":"searchContents","docNo":docno}).decode("utf8")
    src = re.search(r"'(https://kind\.krx\.co\.kr/external/[^']+\.htm)'", frame)
    if not src:
        return
    blob = fetch(folder/"body.html", src[1])
    text = clean(html(blob).get_text(" ",strip=True))
    dump(folder/"body.json",{**r,"text":text,"url":src[1],"sha256":digest(blob)})


def issuer_applications():
    url = KIND + "/listinvstg/listinvstgcom.do"
    folder = SOURCE / "ipo"
    form = html(fetch(folder/"form.html",url,{"method":"searchListInvstgCorpMain"})).select_one("#searchForm")
    p = {o["name"]:o.get("value","") for o in form.select("input[name]")
         if o.get("type") not in ("checkbox","radio") or o.has_attr("checked")}
    p.update(method="searchListInvstgCorpSub",currentPageSize="500",pageIndex="1",forward="listinvstgcom_sub")
    names = {"엘지씨엔에스":"LG씨엔에스","엘지씨앤에스":"LG씨엔에스","위너스":"위너스일렉",
             "벡트":"벡트로보틱스","인스웨이브":"인스웨이브시스템즈","에이치디현대마린솔루션":"HD현대마린솔루션"}
    roster = {r["issuer"]:r for r in read(ROSTER)["rows"]}
    known = {}
    for y in range(2022,2026):
        p.update(fromDate=f"{y}-01-01",toDate=f"{y}-12-31")
        for tr in html(fetch(folder/f"{y}.html",url,p,True)).select("tbody tr[onclick]"):
            cells = tr.select("td")
            name = cells[0]["title"]
            name = names.get(name,name)
            if name not in roster or not cells[2].get_text(strip=True) < roster[name]["date_kst"]:
                continue
            no = re.search(r"'(\d+)'",tr["onclick"])[1]
            date_applied = cells[2].get_text(strip=True)
            source_url = url + "?method=searchListInvstgCorpDetail&bizProcNo=" + no
            blob = fetch(folder/f"{no}.html", source_url)
            doc = html(blob)
            header = next((th for th in doc.select("th") if th.get_text(strip=True) == "업종"), None)
            if not header:
                continue
            result = {"industry": header.find_next_sibling("td").get_text(" ",strip=True),
                      "market":cells[0].img["alt"],"name":name,"submitted":date_applied,
                      "date_precision":"day","sha256":digest(blob),"url":source_url,
                      "snapshot":(folder/f"{no}.html").relative_to(SOURCE.parent).as_posix()}
            key = roster[name]["receipt"]
            if result["submitted"] > known.get(key,{}).get("submitted",""):
                known[key] = result
    dump(folder/"issuers.json", known)
    return known


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-authorized",action="store_true",help="Use when the exchange permits the collection")
    if not parser.parse_args().collect_authorized:
        print("Archived membership manifests:",len(list((SOURCE/"membership").glob("*/*.json"))))
        return
    archives()
    dates = sorted({r["date_kst"] for r in read(ROSTER)["rows"]})
    with ThreadPoolExecutor(max_workers=5) as ex:
        market_jobs = [ex.submit(market, (cut, market_id)) for cut in dates for market_id in ("STK","KSQ")]
        records = []
        for yr in (2022,2023,2024,2025):
            records.extend(changes(f"{yr}-01-01", f"{yr}-12-31"))
        notice_jobs = [ex.submit(notice, r) for r in records]
        failures = []
        for f in market_jobs + notice_jobs:
            try:
                f.result()
            except (httpx.HTTPError, ValueError, KeyError) as e:
                failures.append(str(e))
    print("Fetched",len(dates),"market dates and",len(records),"exchange notices. Errors:",failures)


if __name__ == "__main__":
    main()
