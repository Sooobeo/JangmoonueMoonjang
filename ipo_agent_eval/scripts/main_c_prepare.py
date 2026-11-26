"""Build and audit blinded C inputs from frozen, local evidence (no network)."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from functools import cache

import fitz
from bs4 import BeautifulSoup

from scripts.main_c_market import corp_rows
from scripts.main_c_reports import BASE, SOURCE, ROSTER, read, dump, digest, clean, norm, kind_names

# Verified page/industry anchors in original filings. Where absent use the
# independently published, pre-filing exchange application for the issuer.
# The target field is the KSIC three-digit class, never the five-digit subclass.
SPECS = {
    "에스엘에스바이오":(215,"M72919","기타 과학기술 서비스업"),
    "에코아이":(224,"M72122","건축기술, 엔지니어링 및 관련 기술 서비스업"),
    "한싹":(222,"J58221","소프트웨어 개발 및 공급업"),
    "인스웨이브시스템즈":(255,"J58222","소프트웨어 개발 및 공급업"),
    "에스와이스틸텍":(181,"C25100","구조용 금속제품, 탱크 및 증기발생기 제조업"),
    "에이피알":(245,"C20423","기타 화학제품 제조업"),
    "산일전기":(244,"C28112","전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업"),
    "전진건설로봇":(183,"C30201","자동차 차체 및 트레일러 제조업"),
    "사이냅소프트":(160,"J58222","소프트웨어 개발 및 공급업"),
    "벡트로보틱스":(160,"C26519","영상 및 음향기기 제조업"),
    "모티브링크":(136,"C26293","전자부품 제조업"),
    "피아이이":(190,"C29299","특수 목적용 기계 제조업"),
    "위너스일렉":(212,"C28123","전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업"),
    "레뷰코퍼레이션":(300,"M71310","광고업"),
    "노브랜드":(280,"C14300","편조의복 제조업"),
    "엘케이켐":(143,"C20499","기타 화학제품 제조업"),
    "이노테크":(221,"C29299","특수 목적용 기계 제조업"),
    "세나테크놀로지":(205,"C264","통신 및 방송 장비 제조업"),
    "비아이매트릭스":(121,"J58222","소프트웨어 개발 및 공급업"),
    "티디에스팜":(196,"C21210","의약품 제조업"),
    "아로마티카":(227,"C20423","기타 화학제품 제조업"),
    "워트":(170,"C29271","특수 목적용 기계 제조업"),
    "원일티엔아이":(175,"C29174","일반 목적용 기계 제조업"),
    "씨엠티엑스":(197,"C26299","전자부품 제조업"),
    "바이오비쥬":(180,"C27199","의료용 기기 제조업"),
    "삼진식품":(214,"C10211","수산물 가공 및 저장 처리업"),
    "유진테크놀로지":(209,"C29294","특수 목적용 기계 제조업"),
    "달바글로벌":(171,"C20423","기타 화학제품 제조업"),
    "액스비스":(258,"C28909","기타 전기장비 제조업"),
    "스톰테크":(181,"C22210","플라스틱제품 제조업"),
    "키스트론":(164,"C28302","절연선 및 케이블 제조업"),
}
KST = timezone(timedelta(hours=9))


@cache
def applications():
    out = {}
    for path in (SOURCE/"ipo").glob("??????????????.html"):
        doc = BeautifulSoup(path.read_bytes(),"lxml")
        fields = {s.get_text(strip=True):s.find_next_sibling("td").get_text(" ",strip=True)
                  for s in doc.select("th") if s.find_next_sibling("td")}
        if "업종" in fields and fields.get("심사청구일"):
            out[norm(fields["회사명"])] = {"industry":fields["업종"], "published":fields["심사청구일"],
                "precision":"day", "snapshot":path.relative_to(BASE).as_posix(),"sha256":digest(path.read_bytes()),
                "url":"https://kind.krx.co.kr/listinvstg/listinvstgcom.do?method=searchListInvstgCorpDetail&bizProcNo="+path.stem}
    return out


def industry(row, doc):
    app = applications().get(norm(row["issuer"]))
    if app and app["published"] >= row["date_kst"]:
        app = None
    if row["issuer"] in SPECS:
        page, code, label = SPECS[row["issuer"]]
        text = doc[page-1].get_text(sort=True)
        hit = re.search(r"\s*".join(re.escape(c) for c in code),text)
        if hit:
            return {"industry":label,"ksic":code[:4],"physical_page":page,"quote":text[max(0,hit.start()-140):hit.end()+72],
                "source":"frozen issuer prospectus","sha256":row["pdf_sha256"],"also_checked":app}
    aux=SOURCE/"issuer_sector_aux.json"
    if aux.exists() and row["receipt"] in read(aux):
        entry=read(aux)[row["receipt"]]
        if entry["published"].replace("-","") < row["date_kst"].replace("-","") and digest((BASE/entry["snapshot"]).read_bytes()) == entry["sha256"]:
            return entry
    return app


def label_key(s):
    return re.sub(r"[\s\W_]", "", s).replace("차체나트레일러", "차체및트레일러").replace("그밖의","그외")


@cache
def exchange_snapshot(stamp):
    path = SOURCE/"kind"/(stamp+".html")
    return {r["종목코드"]:r for r in corp_rows(path.read_bytes())}


@cache
def changes():
    paths = sorted((SOURCE/"kind_changes").glob("????-01-01.json"))
    return [row for path in paths for row in read(path)["rows"]]


def crosswalk(names, code, label):
    return code in names.get(norm(label), {})


@cache
def counterpart_members(cutoff, target):
    import pyarrow.parquet as pq
    from datetime import date
    prev=date.fromisoformat(cutoff)-timedelta(days=1)
    path=SOURCE/"membership_mirror"/f"{prev.year}.parquet"
    if not path.exists():return [],{}
    for offset in range(9):
        day=prev-timedelta(days=offset)
        ts=datetime.combine(day,datetime.min.time())
        t=pq.read_table(path,columns=["Code","Name","MarketId"],filters=[("Date","=",ts)])
        if t.num_rows:
            # The authorized public KRX quote archive includes KONEX. Other
            # markets are one protocol group and are sorted together by ticker.
            rows=[{"ticker":r["Code"],"name":r["Name"],"market":r["MarketId"]} for r in t.to_pylist()
                  if r["MarketId"]!=target and not re.search(r"우(?:선주|B|C)?(?:\(전환\))?$",r["Name"])]
            return rows,{"as_of":day.isoformat(),"snapshot":path.relative_to(BASE).as_posix(),
                "sha256":digest(path.read_bytes()),"url":path.with_suffix(".url").read_text().strip()}
    return [],{}


def selection(row, profile, mkt, originals, names, other=False):
    cutoff = row["date_kst"]
    stamps = [f.stem for f in (SOURCE/"kind").glob("??????????????.html")
              if datetime.strptime(f.stem,"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(KST).date().isoformat() < cutoff]
    if not profile or not stamps or not mkt:
        return {"reason":"issuer industry, intended market or historical KIND classification snapshot unavailable"}
    stamp = max(stamps)
    baseline = exchange_snapshot(stamp)
    basepath=SOURCE/"kind"/(stamp+".html")
    rec = {"industry":profile["industry"],"target_market":mkt,"class_snapshot":basepath.relative_to(BASE).as_posix(),
           "class_sha256":digest(basepath.read_bytes()),"captured_utc":stamp,"order_issues":[],"verified_changes":[]}
    mpath = SOURCE/"membership"/cutoff/(mkt+".json")
    if other:
        members,extra_meta=counterpart_members(cutoff,mkt)
        if not members:return {**rec,"reason":"missing other-market historical constituents (incl. KONEX)"}
        membership={**extra_meta,"rows":members}
        rec["market_group"]="other domestic markets"
    elif not mpath.exists():
        return {**rec,"reason":"missing dated KRX membership export"}
    else:membership=read(mpath)
    if digest((BASE/membership["snapshot"]).read_bytes())!=membership["sha256"]:
        raise ValueError("KIND membership hash mismatch")
    rec.update(membership={k:v for k,v in membership.items() if k!="rows"})
    # At minimum investigate every lower-code company before selecting one.
    # Notices after the prior snapshot can invalidate a prior classification.
    base_date = datetime.strptime(stamp,"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(KST).date().isoformat()
    events = sorted((r for r in changes() if base_date <= r["published"][:10] < cutoff),
                    key=lambda r:r["published"])
    sorted_candidates = []
    additions_path=SOURCE/"new_listings.json"
    additions=read(additions_path) if additions_path.exists() else {}
    for path in sorted((SOURCE/"new_listings_secondary").glob("*.json")):
        entry=read(path)
        additions.setdefault(entry["ticker"],[]).append(entry)
    review=SOURCE/"new_listing_notices"/"068100-review.json"
    if review.is_file() and "068100" not in additions:
        entry=read(review)
        # Both contemporaneous sources exclude C143 even though one describes
        # exchange industry and one describes the issuer's DART KSIC.
        if profile.get("ksic")=="C143":
            additions["068100"]=[{**entry,"classification_use":"C291 and J639 both exclude C143"}]
    for member in sorted(membership["rows"],key=lambda x:x["ticker"]):
        ticker,name = member["ticker"],member["name"]
        if ticker in originals or norm(row["issuer"])==norm(name): continue
        if ticker not in baseline:
            extra_entries=additions.get(ticker,[])
            if isinstance(extra_entries,dict):extra_entries=[extra_entries]
            valid=[v for v in extra_entries if v["published"].replace("-","")<cutoff.replace("-","") and
                   digest((BASE/v["snapshot"]).read_bytes())==v["sha256"]]
            if not valid:
                rec["order_issues"].append({"ticker":ticker,"name":name,"reason":"addition since industry snapshot; cutoff classification unverified"})
                continue
            current=max(valid,key=lambda v:v["published"])
            previous={"회사명":name,"업종":current["industry"]}
            rec.setdefault("verified_additions",[]).append({"ticker":ticker,**current})
        else:previous=baseline[ticker]
        label=previous["업종"]
        for event in events:
            if norm(event["name"]) not in (norm(previous["회사명"]),norm(name)) and not crosswalk(names,ticker,event["name"]):
                continue
            body = SOURCE/"kind_changes"/event["receipt"]/"body.json"
            bodytext=read(body)["text"] if body.exists() else ""
            new=(re.search(r"변경후.*?소분류\s*:\s*(.+?)\s+[0-9]{2}-\d{2}-\d{2}",bodytext)
                 or re.search(r"변경\s*후\s*업종\s+(.+?)\s+업종코드\s+\d{6}",bodytext))
            effective=re.search(r"변경일\s*(\d{4}-\d{2}-\d{2})",bodytext)
            if new and effective:
                if effective[1] <= cutoff: label=new[1]
                record=read(body)
                rec["verified_changes"].append({"ticker":ticker,"receipt":event["receipt"],"published":event["published"],
                    "effective":effective[1],"new_industry":new[1],"url":record["url"],"sha256":record["sha256"]})
            else:
                rec["order_issues"].append({"ticker":ticker,"name":name,"receipt":event["receipt"],
                                           "reason":"industry-change effective date and class unverified"})
        issuer_class=profile.get("candidate_classification",{}).get(ticker)
        if issuer_class:
            rec.setdefault("issuer_classifications",[]).append({"ticker":ticker,"earlier_exchange_label":label,**issuer_class})
            label=issuer_class["industry"]
        if label_key(label)==label_key(profile["industry"]):
            sorted_candidates.append({"name":name,"ticker":ticker,"cutoff":cutoff,"market":member.get("market",mkt),
                "historical_name":previous["회사명"],"industry":label})
            evidence=candidate_report(cutoff,ticker)
            if report_facts(evidence)["business"]:
                rec["selected_ticker"]=ticker
                break
            rec.setdefault("candidates_without_business",[]).append({"ticker":ticker,"name":name,
                "reason":evidence.get("issue","no eligible business or product excerpt in the recovered report"),
                "source_checks":evidence.get("source_checks",[])})
    rec["eligible_from_archived_classes"] = sorted_candidates
    if not rec.get("selected_ticker") and not other:
        expanded=selection(row,profile,mkt,originals,names,True)
        rec["other_market_search"]=expanded
        rec["eligible_from_archived_classes"]+=expanded.get("eligible_from_archived_classes",[])
        rec["selected_ticker"]=expanded.get("selected_ticker")
    return rec


def issuer_facts(row, doc):
    toc=doc.get_toc()
    out=[]
    for title in ("1.사업의개요","2.주요제품및서비스","1.요약재무정보"):
        pages=[p for _,t,p in toc if norm(t)==title]
        if not pages:continue
        next_section=next((p for level,t,p in toc if p>pages[-1] and level<=2), len(doc)+1)
        for page in range(pages[-1],min(next_section,pages[-1]+12,len(doc)+1)):
            text=doc[page-1].get_text(sort=True)
            if title=="1.요약재무정보":
                # Quote actual contiguous accounting-period lines and net income rows,
                # preserving their distinct source positions across a continued table.
                blocks=[]
                lines=text.splitlines()
                for ix,line in enumerate(lines):
                    if re.search(r"당기순이익|반기순이익|분기순이익|지배기업.*순이익",line) and re.search(r"\d{1,3},\d{3}",line):
                        heads=[v.strip() for v in lines[:ix] if re.search(r"20\d\d[.년]|제\s*\d+\s*기",v)]
                        meta={"physical_page":page,"location":title,"sha256":row["pdf_sha256"],
                              "url":row["pdf_url"],"receipt":row["receipt"],"published":row["date_kst"],"precision":"day"}
                        units=re.findall(r"단\s*위\s*[:：]\s*(?:백만원|천원|원|억원)","\n".join(lines[:ix]))
                        upage=page
                        if not units and page>1:
                            upage=page-1
                            units=re.findall(r"단\s*위\s*[:：]\s*(?:백만원|천원|원|억원)",doc[upage-1].get_text(sort=True))
                        if units:out.append({**meta,"quote":units[-1],"physical_page":upage})
                        if heads:out.append({**meta,"quote":heads[-1]})
                        out.append({**meta,"quote":line.strip()})
                        break
                else:continue
                break
            else:
                blocks=[b for b in re.split(r"\n\s*\n",text) if len(clean(b))>45 and
                        re.search(r"당사|동사|연결회사|회사.{0,2}(는|의)|주된\s*사업|주요\s*제품은",b) and
                        re.search("제조|판매|제공|서비스|개발|생산|사업을|사업은",b)]
            for block in blocks:
                if re.search("희망공모|비교기업|공모가격|유사회사|기준주가|접수번호|전자공시시스템",block): continue
                if any(norm(block) == norm(x["quote"]) for x in out):continue
                out.append({"quote":block.strip(),"physical_page":page,"location":title,
                            "sha256":row["pdf_sha256"],"url":row["pdf_url"],"receipt":row["receipt"],
                            "published":row["date_kst"],"precision":"day"})
                break
            else:continue
            break
    return out


def business_excerpt(quote, element, headers, report):
    visible=quote[:350]
    if element.name=="tr":
        if (element.find("th")
            or len(visible)<8 or not element.find_all("td") or re.search(r"^(소\s*계|합\s*계|총\s*계|구\s*분|사업부문\s*매출유형)",visible)
            or re.match(r"^(내수|수출|매출액|금액|비율|합계)\s",visible)
            or re.search(r"주요\s*(상표|제품)|대분류\s*소분류|사업부문\s*(품목|제품명|상표|매출액)|매출\s*분류\s*유형|매출\s*유형.{0,8}품\s*목|^품\s*목\s+20[0-9]{2}|단\s*위\s*:|제품\s*종류\s*기능|사\s*업\s*부\s*문\s*표준산업",visible)):
            return False
        return bool(re.search(r"제품|품\s*목|사업내용|사업\s*부문|사업분류|사업영역",headers)
                    and not re.search(r"주요\s*(제\s*품|상표)|단\s*위\s*:",visible)
                    and re.search(r"[가-힣]{2,}",visible))
    if len(visible)<24 or re.search(r"자세한|상세한 내용|기재를 생략|기재되어|상세히 기재|참고하시|참조하시|판매단가|가격변동|제품 가격 추이|용어의 정의|산출기준|아래의 사업을 영위중|사업분류는 다음|각 사업은 별도로 운영|해당사항.{0,3}없",visible):
        return False
    if len(visible)<70 and re.search(r"다음과 같습니다|아래와 같습니다",visible):return False
    owner=r"당사|동사|(?<![가-힣])(?:연결)?회사[는가의]|종속회사|사업부(?:문)?[는의]|"+re.escape(report.get("name") or "해당법인")
    activity=r"사업|제품|서비스|판매|생산|공급|제조|개발|가공|유통|제공|의약품|솔루션|위탁|운영"
    return bool(re.search(owner,visible[:195]) and re.search(activity,visible) and
                not re.search(r"당사가 속한 산업|업계.{0,3}(동향|전망)|시장.{0,5}(전망|예상)",visible[:90]))


def report_facts(report):
    result={"business":[],"financials":[]}
    review=reviewed_business().get(report.get("receipt"),{})
    curated=review.get("business")
    for section in report.get("sections",[]):
        path=BASE/section["snapshot"]
        blob=path.read_bytes()
        if digest(blob)!=section["sha256"]:raise ValueError("Candidate section hash mismatch")
        doc=BeautifulSoup(blob,"lxml",from_encoding="utf8")
        for idx,el in enumerate(doc.select("p,tr"),1):
            if el.name=="p" and el.find_parent("table"):continue
            quote=clean(el.get_text(" ",strip=True))
            if not quote: continue
            meta={**section,"receipt":report["receipt"],"period":report["period"],"published":report["published"],
                  "precision":"day","location":f"{section['section']} / {el.name} {idx}","quote":quote}
            headers=""
            if (el.name=="p" and len(result["financials"])<2
                and re.search(r"(당사|동사|연결회사|주요\s*매출처|사업부문)",quote[:350])
                and re.search(r"매출.{0,15}(구성|비중)|(?:총|전체)\s*매출.{0,15}\d[\d.]*\s*%|매출의\s*\d[\d.]*\s*%",quote[:350])
                and re.search(r"\d[\d.]*\s*%",quote[:350])):
                result["financials"].append(meta)
            if el.name=="tr":
                tb=el.find_parent("table")
                if tb is None:continue
                rows=tb.select("tr")
                headers=clean(" ".join(r.get_text(" ",strip=True) for r in rows[:2]))
                heads=[clean(r.get_text(" ",strip=True)) for r in rows[:4]
                       if re.search(r"비율|비중|매출액|20\d{2}년|제\s*\d+\s*기",r.get_text())]
                table_text=clean(tb.get_text(" ",strip=True))
                is_sales=re.search(r"매출액|누적\s*매출|매출\s*(비율|비중|유형|실적|구성)|수익\s*비중",table_text[:520])
                ratio=re.search(r"\d[\d.]*\s*%",quote)
                amount=re.search(r"\d{1,3},\d{3}",quote)
                if (len(result["financials"])<2 and heads and is_sales and (ratio or amount)
                    and re.search(r"[가-힣]{2,}|[A-Za-z]{2,}",quote)
                    and not re.search(r"영업[이손]|당기순|법인세|매출원가|매출총[이손]|자산총계|부채총계|자본총계|EBITDA",quote)
                    and not re.search(r"^(합\s*계|소\s*계|계\s|총\s*계)",quote)
                    and not re.search(r"매출유형|주요상표|주요제품|주요\s*제품\s*및\s*서비스|구\s*분.{0,10}품\s*목",quote)):
                    if re.match(r"^(비율|비중|금액)\s",quote):
                        prev=el.find_previous_sibling("tr")
                        if prev: heads=[*heads,clean(prev.get_text(" ",strip=True))]
                    result["financials"].append({**meta,"table_headers":heads})
            if curated is not None:continue
            if len(result["business"])>=2:continue
            if business_excerpt(quote,el,headers,report):
                result["business"].append(meta)
    if curated is not None:
        result["business"]=[curated_fact(report,hint) for hint in curated]
    if "financials" in review:
        result["financials"]=[curated_fact(report,hint,financial=True) for hint in review["financials"]]
    return result


@cache
def reviewed_business():
    path=SOURCE/"curated_paragraphs.json"
    entries=read(path) if path.exists() else {}
    sales=SOURCE/"curated_sales.json"
    if sales.exists():
        for receipt,facts in read(sales).items():
            entries.setdefault(receipt,{}).setdefault("financials",facts)
    return entries


def curated_fact(report,hint,financial=False):
    path=BASE/hint["snapshot"]
    index=next((p/"report.json" for p in (path.parent,path.parent.parent) if (p/"report.json").is_file()),None)
    if index is None:raise ValueError("Reviewed section has no filing record")
    original=read(index)
    if original["receipt"]!=report["receipt"]:raise ValueError("Reviewed section belongs to another receipt")
    sec=next(s for s in original["sections"] if s["snapshot"]==hint["snapshot"] and s["section"]==hint["section"])
    raw=path.read_bytes()
    if digest(raw)!=sec["sha256"]:raise ValueError("Reviewed section changed")
    elements=BeautifulSoup(raw,"lxml",from_encoding="utf8").select("p,tr")
    el=elements[hint["row_index"]-1]
    full=clean(el.get_text(" ",strip=True))
    start=full.index(hint["start_at"]) if hint.get("start_at") else 0
    result={**sec,"receipt":report["receipt"],"period":report["period"],"published":report["published"],
            "precision":"day","location":f"{sec['section']} / {el.name} {hint['row_index']}",
            "full_paragraph":full,"excerpt_offset":start,"quote":full[start:]}
    if financial and el.name=="tr" and (table:=el.find_parent("table")):
        result["table_headers"]=[clean(elements[i-1].get_text(" ",strip=True)) for i in hint.get("header_rows",[])]
        result["header_rows"]=hint.get("header_rows",[])
    return result


def candidate_report(cutoff,ticker):
    tried=[];checks=[]
    for directory in ("opendart_reports","reports","archive_reports"):
        record=SOURCE/directory/cutoff/ticker/"report.json"
        if record.exists():
            report=read(record)
            if report.get("sections") and report.get("published","").replace("-","") < cutoff.replace("-",""):
                return report
            tried.append(report.get("issue","no verified prior sections"))
            checks.append({"snapshot":record.relative_to(BASE).as_posix(),"sha256":digest(record.read_bytes())})
    evidence=SOURCE/"opendart_xbrl"/ticker/"provenance.json"
    if evidence.is_file():
        check=read(evidence)
        if check["published"]<cutoff.replace("-",""):
            checks.append({"snapshot":evidence.relative_to(BASE).as_posix(),"sha256":digest(evidence.read_bytes()),
                           "receipt":check["receipt"],"published":check["published"]})
            tried.append(check.get("bulk_check",check["limitations"]))
    return {"issue":"; ".join(filter(None,tried)) or "own pre-cutoff periodic report not yet retrieved","source_checks":checks}


@cache
def listed_name_pattern():
    known={n for n in kind_names() if len(n)>=3} - {"디바이스","타이드","new","emb","mit"}
    known.update(["openai","국민은행","기업은행","신한은행","인젠트","에이유커머스","sk온","삼성sdi","삼성전자",
                  "디포커스","lg전자","lg화학","애플","한국투자증권","하나증권","daeati","daea ti","대아글로벌","fasoo","classys",
                  "verismo therapeutics","한성수산식품","한성식품","한불화장품","포스코디엑스","오션 주식회사","칼라앤터치",
                  "한세예스24홀딩스","siemens","아큐시네트","acushnet","우리은행","대림수산","사조그룹","사조해표",
                  "fila","한영정공","삼화페인트공업","한컴","미래에셋증권","한화투자증권","스패로우","sparrow",
                  "큐브엔터테인먼트","삼진어묵","주식회사 지엠피","한영정공","제일전기공업","포스코아이씨티",
                  "APR","Advance People's Real life","CLIO","codes-combine","codes combine","ksign"])
    def company_name(n):
        if n=="애플":return r"애플(?!리케이션)"
        if n.isascii() and len(n)<=3:return alias_pattern(n)
        return re.escape(n)
    return re.compile("|".join(company_name(n) for n in sorted(known,key=lambda s:(-len(s),s))),re.I)


def mask(fact, aliases):
    replacements={}
    value=fact.get("text") or clean(fact["quote"])
    if fact.get("section_heading_quote") and fact["field"]=="financials":
        value=clean(fact["section_heading_quote"])+" · "+value
    if fact.get("period") and fact.get("field")=="financials":
        headers=[s for s in fact.get("table_headers",[]) if len(s)<=130 and s != value and not re.search(r"\d[\d.]*\s*%",s)]
        header=" / ".join(dict.fromkeys(headers))[:125]
        value=fact["period"]+" 보고기간 · "+(header+" · " if header else "")+value
    def replace(match):
        replacements[match[0]]="[기업]"
        return "[기업]"
    value=listed_name_pattern().sub(replace,value)
    value=re.sub(r"보성(?=\s*제품매출)",replace,value)
    value=re.sub(r"[㈜]\s*[A-Za-z가-힣][A-Za-z가-힣0-9&]{1,28}?(?=\s|\(|는|은|와|과|의|을|를|$)",replace,value)
    value=re.sub(r"(?i)\b(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|co\.kr|io)(?:/\S*)?\b","[주소]",value)
    for alias in sorted(aliases,key=len,reverse=True):
        if alias:value=re.sub(alias_pattern(alias),replace,value,flags=re.I)
    value=re.sub(r"https?://\S+", "[주소]",value)
    return value[:350],replacements


def alias_pattern(term):
    body=r"\s*".join(re.escape(c) for c in term if not c.isspace())
    return r"(?<![A-Za-z])"+body+r"(?![A-Za-z])" if term.isascii() and term.isalpha() and len(term)<=3 else body


def build(row,names):
    if (BASE/"freeze.json").exists():raise ValueError("C inputs are already frozen")
    key=row["receipt"];folder=BASE/"issuers"/key
    items=read(folder/"items.json")
    peers=[r for r in items if r["family"]=="J2"]
    aliases={row["issuer"],row["corp_code"],key,*[r["target"] for r in peers]}
    foreign_path=SOURCE/"foreign.json"
    foreign=read(foreign_path).get(key,{}) if foreign_path.exists() else {}
    records, issues, originals = [], [], set()
    for item in peers:
        name=item["target"]; ids=names.get(norm(name),{})
        if len(ids)==1:
            ticker=next(iter(ids)); originals.add(ticker)
            report=candidate_report(row["date_kst"],ticker)
            aliases.update([ticker,report.get("name","")])
            detail=report_facts(report)
            if not detail["business"]:
                issues.append({"item_id":item["id"],"name":name,"ticker":ticker,
                               "reason":report.get("issue","business excerpt not verified"),
                               "source_checks":report.get("source_checks",[]),"origin":"domestic"})
                continue
            records.append({"name":name,"ticker":ticker,"item_id":item["id"],"source_report":report,**detail})
        else:
            data=foreign.get(name,{})
            if not data.get("business"):
                issues.append({"name":name,"item_id":item["id"],"origin":"foreign","reason":data.get("issue","foreign latest periodic report and excerpts pending")})
            else:
                identity={k:data[k] for k in ("receipt","published","period","title") if k in data}
                records.append({"name":name,"item_id":item["id"],**data,
                    "source_report":{k:v for k,v in data.items() if k not in ("financials","business")},
                    "business":[{**identity,**v} for v in data["business"]],
                    "financials":[{**identity,**v} for v in data.get("financials",[])]})
    with fitz.open(ROSTER.parent/row["pdf_file"]) as doc:
        profile=industry(row,doc);issuer=issuer_facts(row,doc)
        if key=="20240710000686":
            page=184
            text=clean(doc[page-1].get_text(sort=True))
            quote=re.search(r"차체 및 특장차 제조업\s*\(C30201\)의 상장기업.*?광림 1개\s*사만 존재",text)
            if not quote:raise ValueError("Prospectus KSIC classification no longer verifiable")
            profile["candidate_classification"]={"014200":{"industry":profile["industry"],"ksic":"C30201",
                "receipt":key,"physical_page":page,"quote":quote[0],"sha256":row["pdf_sha256"],
                "url":row["pdf_url"],"published":row["date_kst"],"precision":"issuer original",
                "source":"Latest explicit KSIC in frozen prospectus; independent market membership required."}}
        page=row["ipo_status_anchor"]["page"]
        txt=norm(doc[page-1].get_text(sort=True))
        market="KSQ" if "코스닥시장상장" in txt else ("STK" if "유가증권시장상장" in txt else None)
    choice=selection(row,profile,market,originals,names)
    option=next((v for v in choice.get("eligible_from_archived_classes",[]) if v["ticker"]==choice.get("selected_ticker")),None)
    reasons=[]
    if not issuer:reasons.append("issuer business evidence missing")
    if not option:reasons.append(choice.get("reason","same and other domestic markets searched; no supplemental candidate with verified pre-filing business evidence"))
    else:
        if "other_market_search" in choice:
            lower=choice["order_issues"]+[x for x in choice["other_market_search"]["order_issues"] if x["ticker"]<=option["ticker"]]
        else:lower=[x for x in choice["order_issues"] if x["ticker"]<=option["ticker"]]
        if lower:reasons.append(f"same-market order: {len(lower)} companies at/below first candidate have unresolved historical industry")
        report=candidate_report(row["date_kst"],option["ticker"])
        detail=report_facts(report)
        if detail["business"]:
            records.append({**option,"item_id":None,"source_report":report,**detail})
        else:reasons.append("first same-market supplementary candidate's latest periodic report/business excerpt unverified")
    for issue in issues:
        issue["c_assessment"]="미확인·자료 부족"
        issue["excluded_from_wire"]=True
    out={"issuer_evidence":[],"candidates":[]};sources={}; links={}
    aliases.update(x.get("name","") for x in records)
    aliases.update(x["ticker"] for x in records if len(x["ticker"])>=5)
    def append(facts,field):
        result=[]
        for fact in facts:
            fact={**fact,"field":field}
            val,changes=mask(fact,aliases)
            eid=f"E{len(sources)+1}"
            sources[eid]={**fact,"redactions":changes,"masked_excerpt":val}
            result.append({"evidence_id":eid,"text":val})
        return result
    out["issuer_evidence"]=append(issuer,"issuer")
    records.sort(key=lambda x:hashlib.sha256(f"{key}/{x['ticker']}".encode()).hexdigest())
    for n,r in enumerate(records,1):
        cid=f"C{n}"
        links[cid]={"name":r["name"],"ticker":r["ticker"],"item_id":r["item_id"],"supplementary":r["item_id"] is None}
        out["candidates"].append({"candidate_id":cid,"business":append(r["business"],"business"),
                                  "financials":append(r.get("financials",[]),"financials"),"multiples":[]})
    texts=[s["masked_excerpt"] for s in sources.values()]
    leaks=[n for n in ("http://","https://","접수번호","공모가","비교회사","유사회사","비교기업",*aliases)
           if n and len(n)>1 and any(re.search(alias_pattern(n),v,re.I) for v in texts)]
    if leaks:reasons.append("wire identity/selection indicators unresolved: "+", ".join(sorted(set(leaks))))
    if not any(x["supplementary"] for x in links.values()) and peers:reasons.append("supplementary candidate not in blinded packet")
    status={"receipt":key,"ready":not reasons,"j2_applicability":"applicable" if peers else "not_applicable",
            "original_j2":len(peers),"original_with_business":sum(x["item_id"] is not None for x in records),
            "issuer_excerpts":len(issuer),"supplementary_ticker":option["ticker"] if option else None,
            "excluded_j2":issues,"reasons":reasons}
    private={"receipt":key,"cutoff":row["date_kst"],"sector":profile,"market_search":choice,"links":links,
             "sources":sources,"candidate_issues":issues,"draft":out,
             "candidate_documents":{r["ticker"]:r.get("source_report",{}) for r in records},
             "identifiability":"specific products and issuer facts can suggest company identity"}
    dump(folder/"c_private.json",private)
    if status["ready"]:
        from ipo_eval.blind_reviewer import load_packet
        dump(folder/"c.json",out)
        load_packet(folder/"c.json",digest((folder/"c.json").read_bytes()))
    elif (folder/"c.json").exists():
        old=folder/"c.json"
        old.replace(folder/("c_unfrozen_"+digest(old.read_bytes())[:16]+".json"))
    dump(folder/"c_status.json",status)
    return status,option


def main():
    rows=[];extras=[];names=kind_names()
    for r in read(ROSTER)["rows"]:
        status,extra=build(r,names);rows.append(status)
        if extra:extras.append(extra)
    dump(SOURCE/"supplementary_search_queue.json",extras)
    dump(BASE/"c_preparation.json",{"issuers":len(rows),"ready":sum(r["ready"] for r in rows),
         "original_j2":sum(r["original_j2"] for r in rows),"original_with_business":sum(r["original_with_business"] for r in rows),
         "rows":rows})


if __name__=="__main__":
    main()
