"""Recover dated filing sections from a pinned public mirror of issuer-authored DART XML."""
import argparse
import hashlib
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from scripts.main_c_reports import SOURCE, dump, norm, read

REVISION="72e86bb7483fe0060d3a45c1793237c1bf73f87d"
REPO="https://huggingface.co/datasets/eddmpython/dartlab-data"
FOLDER=SOURCE/"archive_reports"


class RangeFile(io.RawIOBase):
    def __init__(self, client, ticker):
        self.client=client
        self.url=f"{REPO}/resolve/{REVISION}/dart/docs/{ticker}.parquet?download=true"
        r=self.get(self.url)
        if r.status_code >= 400:
            r.raise_for_status()
        self.cdn=r.headers["location"]
        self.size=int(r.headers["x-linked-size"])
        self.source_hash=r.headers["x-linked-etag"].strip('"')
        self.pos=0
        self.cache=[]

    def get(self, url, **options):
        for attempt in range(4):
            try:
                return self.client.get(url, **options)
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(0.5 * (attempt+1))

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos=(0,self.pos,self.size)[whence]+offset
        return self.pos

    def fetch(self,start,stop):
        if start==stop:
            return b""
        for pos,chunk in self.cache:
            if pos<=start and stop<=pos+len(chunk):
                return chunk[start-pos:stop-pos]
        r=self.get(self.cdn,headers={"Range":f"bytes={start}-{stop-1}"})
        if r.status_code!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{stop-1}/{self.size}":
            raise ValueError("Unexpected byte range")
        if len(r.content)!=stop-start:
            raise ValueError("Incomplete archived row group")
        self.cache.append((start,r.content))
        return r.content

    def read(self,n=-1):
        end=self.size if n<0 else min(self.size,self.pos+n)
        chunk=self.fetch(self.pos,end)
        self.pos=end
        return chunk


def recover(ticker, cutoff):
    dest=FOLDER/cutoff/ticker
    if (dest/"report.json").exists() and read(dest/"report.json").get("sections"):
        return "cached"
    with httpx.Client(timeout=25) as client:
        f=RangeFile(client,ticker)
        pqfile=pq.ParquetFile(f)
        cols=pqfile.schema.names
        timeline=[]
        keys=("rcept_no","rcept_date","report_type")
        for idx in range(pqfile.num_row_groups):
            rg=pqfile.metadata.row_group(idx)
            fields=[rg.column(cols.index(key)).statistics for key in keys]
            if all(s and s.has_min_max and s.min==s.max for s in fields):
                values=[tuple(s.min for s in fields)]
            else:
                values=set(tuple(row[k] for k in keys) for row in pqfile.read_row_group(idx,columns=list(keys)).to_pylist())
            for receipt,date,title in values:
                period=re.search(r"\((20\d\d\.\d{2})\)",title or "")
                if period and date<cutoff.replace("-","") and any(kind in title for kind in ("분기보고서","반기보고서","사업보고서")):
                    timeline.append((period[1],date,receipt,title,idx))
        if not timeline:
            return "no_pre_cutoff_periodic_report"
        period,date,receipt,title,_=max(timeline)
        rows=[]
        for idx in sorted({v[-1] for v in timeline if v[2]==receipt}):
            rg=pqfile.metadata.row_group(idx)
            offsets=[(c.dictionary_page_offset if c.has_dictionary_page else c.data_page_offset, c.total_compressed_size)
                     for c in (rg.column(i) for i in range(rg.num_columns))]
            f.fetch(min(off for off,_ in offsets),max(off+size for off,size in offsets))
            rows.extend(row for row in pqfile.read_row_group(idx).to_pylist() if row["rcept_no"]==receipt)
    rows.sort(key=lambda r:r["section_order"])
    if not rows or any(row["stock_code"]!=ticker for row in rows):
        raise ValueError("Ticker or receipt mismatch")
    canonical="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt
    def save(name,content):
        path=dest/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)
        return {"url":canonical,"snapshot":path.relative_to(SOURCE.parent).as_posix(),
                "sha256":hashlib.sha256(content).hexdigest(),"mirror":f.url,"archive_sha256":f.source_hash}
    lead=rows[0]
    cover=save("cover.xml", (lead["section_content"] or "").encode())
    timeline_meta=save("timeline.json",json.dumps(sorted(set(tuple(row[:4]) for row in timeline)),ensure_ascii=False).encode())
    sections=[]
    for row in rows:
        sec=re.sub(r"\([^)]{1,14}업\)", "", norm(row["section_title"] or ""))
        if not sec.startswith(("ii.사업의내용","1.사업의개요","2.주요제품","4.매출및수주","4.매출실적")) or not row["section_content"]:
            continue
        if sec.startswith("ii.") and len(re.sub("<[^>]+>", "", row["section_content"]).strip()) < 10:
            continue
        artifact=save(str(row["section_order"])+".html",row["section_content"].encode())
        sections.append({**artifact,"section":row["section_title"],"document_id":receipt,
                         "section_order":row["section_order"]})
    if not sections:
        # Some archive rows are chunks of a complete filing labelled with its first heading.
        # Match the XML section and its own title rather than prose references or a table of contents.
        body="".join(row["section_content"] or "" for row in rows)
        pattern=r'(<SECTION-2\b[^>]*>\s*<TITLE\b[^>]*>([^<]+)</TITLE>.*?</SECTION-2>)'
        for block,heading in re.findall(pattern,body,flags=re.S|re.I):
            if not norm(heading).startswith(("1.사업의개요","2.주요제품","4.매출및수주","4.매출실적")):
                continue
            artifact=save(f"xml-section-{len(sections)+1}.html",block.encode())
            sections.append({**artifact,"section":heading,"document_id":receipt,
                             "source_location":"original nested SECTION-2 / TITLE in ordered archive chunks"})
    entry={"ticker":ticker,"name":lead["corp_name"],"corp_code":lead["corp_code"],"cutoff":cutoff,
           "receipt":receipt,"period":period,"title":title,"published":date,"published_precision":"day",
           "cutoff_precision_used":"day","cover":cover,"search_snapshots":[timeline_meta],"sections":sections,
           "mirror_attribution":"DartLab / eddmpython, CC BY 4.0; DART issuer-authored filing XML sections",
           "mirror_revision":REVISION}
    dump(dest/"report.json",entry)
    return len(sections)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs",type=Path,help="JSON array of [six-character ticker, ISO cutoff date] pairs")
    args=parser.parse_args()
    if args.pairs:
        tasks=set(map(tuple,read(args.pairs)))
    else:
        tasks={(p.parent.name,p.parent.parent.name) for p in SOURCE.glob("reports/*/*/report.json")
               if not read(p).get("sections")}
    def run(task):
        for retry in (0,1):
            try:
                return [*task,recover(*task)]
            except (httpx.HTTPError, ValueError, KeyError, OSError) as exc:
                if retry:
                    return [*task,type(exc).__name__]
                time.sleep(1)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(run,sorted(tasks)))
    print(json.dumps(results,ensure_ascii=True),flush=True)


if __name__=="__main__":
    main()
