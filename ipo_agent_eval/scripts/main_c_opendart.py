"""Collect historical periodic reports through the user's official OpenDART key."""
import argparse
import io
import os
import re
import time
import zipfile
from datetime import date, timedelta

import httpx
from dotenv import dotenv_values
from lxml import etree

from scripts.main_c_reports import BASE, PEERS, ROOT, ROSTER, SOURCE, digest, dump, kind_names, norm, read


class OpenDartError(Exception):
    """Sanitized error (URLs containing API keys must never enter the archive)."""


def downloaded(client, key, endpoint, query):
    try:
        res = client.get("https://opendart.fss.or.kr/api/"+endpoint,params={"crtfc_key":key,**query})
    except httpx.HTTPError as exc:
        raise OpenDartError(type(exc).__name__) from None
    if res.status_code!=200:
        raise OpenDartError("OpenDART HTTP "+str(res.status_code))
    return res.content


def xmlblob(blob):
    if not blob.startswith(b"PK"):
        try:
            status=etree.fromstring(blob).findtext("status")
        except etree.XMLSyntaxError:
            status=None
        raise OpenDartError("OpenDART status "+str(status))
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        files=[n for n in archive.namelist() if n.lower().endswith(".xml")]
        if not files:raise OpenDartError("ZIP has no XML member")
        # document.xml normally has the main receipt XML plus optional exhibits.
        return {n:archive.read(n) for n in files}


def corp_codes(client,key):
    path=SOURCE/"opendart_master"/"corporations.zip"
    if path.exists():blob=path.read_bytes()
    else:
        blob=downloaded(client,key,"corpCode.xml",{})
        xmlblob(blob)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(blob)
    root=etree.fromstring(next(iter(xmlblob(blob).values())))
    return {node.findtext("stock_code","").strip():node.findtext("corp_code","").strip()
            for node in root.findall("list") if node.findtext("stock_code","").strip()}


def report(client,key,codes,ticker,cutoff):
    dest=SOURCE/"opendart_reports"/cutoff/ticker
    record=dest/"report.json"
    if record.exists() and read(record).get("sections"):return
    dest.mkdir(parents=True,exist_ok=True)
    corp=codes.get(ticker)
    if not corp:raise OpenDartError("Ticker missing from corporate code crosswalk")
    end=date.fromisoformat(cutoff)-timedelta(days=1)
    q={"corp_code":corp,"bgn_de":(end-timedelta(days=550)).strftime("%Y%m%d"),"end_de":end.strftime("%Y%m%d"),
       "pblntf_ty":"A","last_reprt_at":"N","page_count":"100"}
    items=[]; pages=[]
    from json import loads
    for page in range(1,100):
        q["page_no"]=str(page)
        p=dest/f"search-{page}.json"
        blob=p.read_bytes() if p.exists() else downloaded(client,key,"list.json",q)
        result=loads(blob)
        status=result.get("status")
        if status=="013":break
        if status!="000":raise OpenDartError("OpenDART status "+str(status))
        p.write_bytes(blob);pages.append({"sha256":digest(blob),"snapshot":p.relative_to(BASE).as_posix(),
                                          "endpoint":"https://opendart.fss.or.kr/api/list.json","query":dict(q)})
        for x in result["list"]:
            title=x["report_nm"]
            period=re.search(r"\((\d{4}\.\d{2})\)",title)
            if period and "첨부" not in title and re.search("사업보고서|반기보고서|분기보고서",title):
                if x["corp_code"]!=corp or x["rcept_dt"]>q["end_de"]:raise OpenDartError("Out-of-scope receipt")
                items.append((period[1],x["rcept_dt"],x["rcept_no"],x))
        if page>=int(result["total_page"]):break
    if not items:raise OpenDartError("No periodic filings in date window")
    period,published,receipt,filing=max(items)
    origin=SOURCE/"opendart_documents"/(receipt+".zip")
    blob=origin.read_bytes() if origin.is_file() else downloaded(client,key,"document.xml",{"rcept_no":receipt})
    members=xmlblob(blob)
    name=next((n for n in members if n.split("/")[-1].lower()==receipt+".xml"),None)
    if not name and len(members)==1:name=next(iter(members))
    if not name:raise OpenDartError("Main XML member not identified for receipt")
    origin.parent.mkdir(parents=True,exist_ok=True); origin.write_bytes(blob)
    raw=members[name]
    parser=etree.XMLParser(resolve_entities=False,no_network=True,huge_tree=True)
    xml=etree.fromstring(raw,parser)
    out=[]
    for i,section in enumerate(xml.xpath("//*[starts-with(local-name(),'SECTION-')]")):
        title=section.findtext("TITLE","")
        if not any(norm(title).startswith(k) for k in ("1.사업의개요","2.주요제품","4.매출및수주","4.매출실적")):continue
        serialized=etree.tostring(section,encoding="utf8")
        p=dest/f"section-{i}.xml";p.write_bytes(serialized)
        out.append({"section":title,"snapshot":p.relative_to(BASE).as_posix(),"sha256":digest(serialized),
                   "url":"https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt,
                   "section_index":i,"member":name})
    dump(record,{"name":filing["corp_name"],"corp_code":corp,"ticker":ticker,"cutoff":cutoff,
         "published":published,"published_precision":"day","receipt":receipt,"period":period,"title":filing["report_nm"],
         "document":{"zip_sha256":digest(blob),"snapshot":origin.relative_to(BASE).as_posix(),
                     "member_sha256":digest(raw),"member":name},
         "search_snapshots":pages,"sections":out,"issue":None if out else "Latest report has no matching periodic business section"})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only-missing",action="store_true")
    args=parser.parse_args()
    key=os.environ.get("DART_API_KEY") or dotenv_values(ROOT.parent/".env").get("DART_API_KEY")
    if not key:
        print("DART_API_KEY unavailable")
        return
    names=kind_names(); peers=read(PEERS);tasks=set()
    for row in read(ROSTER)["rows"]:
        for name in peers[row["receipt"]]["peers"]:
            ids=names.get(norm(name),{})
            if len(ids)==1:tasks.add((row["date_kst"],next(iter(ids))))
    queue=SOURCE/"supplementary_search_queue.json"
    if queue.exists():tasks.update((x["cutoff"],x["ticker"]) for x in read(queue))
    issues=[]
    with httpx.Client(timeout=30,follow_redirects=False) as client:
        codes=corp_codes(client,key)
        for cutoff,ticker in sorted(tasks):
            cached=SOURCE/"reports"/cutoff/ticker/"report.json"
            if args.only_missing and cached.exists() and read(cached).get("sections"):continue
            try:
                report(client,key,codes,ticker,cutoff)
            except (OpenDartError, etree.XMLSyntaxError, zipfile.BadZipFile) as exc:
                issue=str(exc)
                issues.append({"cutoff":cutoff,"ticker":ticker,"issue":issue})
                if issue in {"OpenDART status "+s for s in ("010","011","012","020","021","800","901")} or "HTTP 429" in issue:
                    break
            time.sleep(0.35)
    dump(SOURCE/"opendart_issues.json",issues)


if __name__=="__main__":
    main()
