"""Collect candidate-owned, cut-off-specific DART periodic reports without any model call."""

import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_main/v1"
SOURCE = BASE / "c_source"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"
PEERS = ROOT / "data/a1_main/valuation_sources.json"
DART = "https://dart.fss.or.kr"
QUERY = DART + "/dsab001/search.ax"
REPORT_TYPES = ("A001", "A002", "A003")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def read(path):
    return json.loads(path.read_bytes())


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def clean(text):
    return " ".join(text.split())


def norm(text):
    return re.sub(r"\s|㈜|\(주\)", "", text).casefold()


def soup(blob):
    return BeautifulSoup(blob, "html.parser", from_encoding="utf8")


def snapshot(client, root, name, url):
    path = root / name
    # Only complete successful responses reach the cache.
    if path.exists():
        blob = path.read_bytes()
    else:
        for attempt in range(4):
            try:
                response = client.get(url, headers={"Referer": DART + "/"})
                break
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(0.7 * (2 ** attempt))
        response.raise_for_status()
        blob = response.content
        if len(blob) < 800 or "서비스 이용에 불편".encode() in blob:
            raise ValueError("DART did not return the requested document")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return blob, {"url": url, "snapshot": path.relative_to(BASE).as_posix(), "sha256": digest(blob)}


def kind_names():
    path = SOURCE / "kind_names.json"
    files = sorted((SOURCE / "kind").glob("*.html"))
    if path.exists() and read(path)["snapshot_names"] == [f.name for f in files]:
        return read(path)["rows"]
    rows = {}
    for f in files:
        html = BeautifulSoup(f.read_bytes(), "lxml")
        table = html.select("table tr")
        fields = [c.get_text(strip=True) for c in table[0].select("th")]
        for row in table[1:]:
            d = dict(zip(fields, [c.get_text(strip=True) for c in row.select("td")]))
            if not re.fullmatch(r"[0-9A-Z]{6}", d.get("종목코드", "")):
                continue
            rows.setdefault(norm(d["회사명"]), {})[d["종목코드"]] = d["회사명"]
    dump(path, {"snapshot_names": [f.name for f in files], "rows": rows})
    return rows


def disclosures(client, dest, ticker, cutoff):
    start = date.fromisoformat(cutoff) - timedelta(days=550)
    end = date.fromisoformat(cutoff) - timedelta(days=1)
    found, searches = [], []
    for kind in REPORT_TYPES:
        query = dict(currentPage=1, maxResults=100, startDate=start.strftime("%Y%m%d"),
                     endDate=end.strftime("%Y%m%d"), textCrpNm=ticker, publicType=kind,
                     sort="date", series="desc")
        blob, meta = snapshot(client, dest, kind + ".html", QUERY + "?" + urlencode(query))
        s = soup(blob)
        count = re.search(r"총\s*([\d,]+)건", s.get_text(" ", strip=True))
        links = s.select('a[href*="rcpNo="]')
        if count and int(count[1].replace(",", "")) != len(links):
            raise ValueError("DART search pagination incomplete")
        if not count and "없습니다" not in s.get_text(strip=True):
            raise ValueError("Unrecognized DART search response")
        searches.append(meta)
        for a in links:
            row = a.find_parent("tr")
            corp = row.select_one('a[onclick*="openCorpInfoNew"]')
            title = clean(a.get_text(" ", strip=True))
            period = re.search(r"\((\d{4}\.\d{2})\)", title)
            if not period or not corp or "첨부" in title:
                continue
            receipt = re.search(r"rcpNo=(\d{14})", a['href'])[1]
            if receipt[:8] > end.strftime("%Y%m%d"):
                raise ValueError("Post-cutoff report")
            found.append({"receipt": receipt, "period": period[1], "title": title,
                          "name": clean(corp.get_text()), "corp_code": re.search(r"'(\d{8})'", corp["onclick"])[1]})
    if len({v["corp_code"] for v in found}) > 1:
        raise ValueError("Ticker search returned multiple corporations")
    return sorted(found, key=lambda v: (v["period"], v["receipt"]), reverse=True), searches


def sections(client, dest, report):
    url = DART + "/dsaf001/main.do?rcpNo=" + report["receipt"]
    blob, meta = snapshot(client, dest, "cover.html", url)
    nodes = []
    for node in re.split(r"var node\d+\s*=\s*\{\};", blob.decode("utf8")):
        f = dict(re.findall(r'''node\d+\['(\w+)'\]\s*=\s*"([^"]*)"''', node))
        title = norm(f.get("text", ""))
        if not any(title.startswith(p) for p in ("1.사업의개요", "2.주요제품", "4.매출및수주", "4.매출실적")):
            continue
        if f["rcpNo"] != report["receipt"]:
            raise ValueError("DART cover points to a different receipt")
        params = {k: f[k] for k in ("rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")}
        _, section = snapshot(client, dest, f["eleId"] + ".html", DART + "/report/viewer.do?" + urlencode(params))
        nodes.append({**section, "section": f["text"], "document_id": f["dcmNo"]})
    return meta, nodes


def collect(task):
    name, ticker, cutoff = task
    dest = SOURCE / "reports" / cutoff / ticker
    record = dest / "report.json"
    if record.exists() and read(record).get("sections"):
        return read(record)
    entry = {"name": name, "ticker": ticker, "cutoff": cutoff,
             "cutoff_precision_used": "day", "published_precision": "day"}
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        try:
            choices, entry["search_snapshots"] = disclosures(client, dest, ticker, cutoff)
            if choices:
                report = choices[0]
                entry.update(report, published=report["receipt"][:8])
                entry["cover"], entry["sections"] = sections(client, dest / report["receipt"], report)
                if not entry["sections"]:
                    entry["issue"] = "No business/product section identified in the latest report"
            else:
                entry["issue"] = "No eligible DART periodic report in the search interval"
        except (httpx.HTTPError, ValueError, KeyError) as e:
            entry["issue"] = f"{type(e).__name__}: {e}"
    dump(record, entry)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra", type=Path, help="Additional rows with name, ticker, cutoff")
    args = parser.parse_args()
    names = kind_names()
    roster = read(ROSTER)["rows"]
    peers = read(PEERS)
    tasks = {}
    missing = []
    for row in roster:
        for name in peers[row["receipt"]]["peers"]:
            ids = names.get(norm(name), {})
            if len(ids) != 1:
                missing.append({"issuer": row["receipt"], "peer": name})
                continue
            ticker = next(iter(ids))
            tasks[row["date_kst"], ticker] = name, ticker, row["date_kst"]
    if args.extra:
        for x in read(args.extra):
            tasks[x["cutoff"], x["ticker"]] = x["name"], x["ticker"], x["cutoff"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(collect, tasks.values()))
    print(json.dumps({"candidate_dates": len(results), "sections_found": sum(bool(v.get("sections")) for v in results),
                      "unresolved_identifiers": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
