"""Three independent offline C checks over prepared/withheld issuer packets."""
import re
import unicodedata
import warnings
from datetime import datetime, timezone, timedelta
from functools import cache

import fitz
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ipo_eval.blind_reviewer import PACKET, load_packet
from jsonschema import validate
from scripts.main_c_reports import BASE, ROSTER, digest, dump, read
from scripts.main_c_prepare import curated_fact, reviewed_business


def compact(s):
    return "".join(unicodedata.normalize("NFKC",s).split()).casefold()


@cache
def file_hash(path):
    return digest(path.read_bytes())


@cache
def contents(path,page=None):
    if path.suffix.lower()==".pdf":
        with fitz.open(path) as pdf:
            indexes=[page-1] if page else range(len(pdf))
            return [compact(pdf[i].get_text(sort=sort)) for i in indexes for sort in (True,False)]
    blob=path.read_bytes()
    # Filed XHTML can carry an XML declaration and HTML entities. Match the
    # rendered visible text used to cite the original SEC/DART filing.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore",XMLParsedAsHTMLWarning)
        doc=BeautifulSoup(blob,"lxml",from_encoding="utf8")
    return [compact(doc.get_text(" ",strip=True))]


def verify(row):
    receipt=row["receipt"]
    folder=BASE/"issuers"/receipt
    record=read(folder/"c_private.json")
    status=read(folder/"c_status.json")
    originals={i["id"] for i in read(folder/"items.json") if i["family"]=="J2"}
    link=record["links"]; sources=record["sources"]
    pkt=record["draft"]
    reviews=[[],[],[]]
    market=record["market_search"]
    for group in [market]+([market["other_market_search"]] if "other_market_search" in market else []):
        m=group.get("membership",{})
        if group.get("class_snapshot") and file_hash(BASE/group["class_snapshot"])!=group["class_sha256"]:
            reviews[0].append("industry universe snapshot digest mismatch")
        if group.get("captured_utc"):
            captured=datetime.strptime(group["captured_utc"],"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            if captured.astimezone(timezone(timedelta(hours=9))).date().isoformat()>=record["cutoff"]:
                reviews[0].append("industry archive not prior to the issuer")
        if m.get("snapshot") and (file_hash(BASE/m["snapshot"])!=m["sha256"] or m.get("as_of","")>=record["cutoff"]):
            reviews[0].append("listing membership digest/time mismatch")
        for addition in group.get("verified_additions",[]):
            if file_hash(BASE/addition["snapshot"])!=addition["sha256"] or addition["published"].replace("-","")>=receipt[:8]:
                reviews[0].append("new listing evidence digest/time mismatch")
    for key, fact in sources.items():
        own=fact.get("receipt")==receipt
        path=ROSTER.parent/row["pdf_file"] if own else BASE/fact["snapshot"]
        if file_hash(path)!=fact["sha256"]:
            reviews[0].append(key+" snapshot digest mismatch")
            continue
        text=compact(fact["quote"])
        if not text or not any(text in hay for hay in contents(path,fact.get("physical_page"))):
            reviews[0].append(key+" source quote not located")
        if not own and (not fact.get("published") or fact["published"].replace("-","") >= receipt[:8]):
            reviews[0].append(key+" source not proven prior to issuer")
    candidate_ids=[x["candidate_id"] for x in pkt["candidates"]]
    expected_order=sorted(link,key=lambda cid:digest((receipt+"/"+link[cid]["ticker"]).encode()))
    if candidate_ids!=expected_order:reviews[1].append("candidate SHA-256 order mismatch")
    included={l["item_id"] for l in link.values() if l["item_id"] is not None}
    omitted={l["item_id"] for l in record["candidate_issues"]}
    if included & omitted or included|omitted!=originals:reviews[1].append("J2 accounting mismatch")
    controls=[v["ticker"] for v in link.values() if v["supplementary"]]
    if controls and controls!=[market.get("selected_ticker")]:reviews[1].append("supplementary candidate differs from first eligible")
    if any(v["ticker"] in controls for v in link.values() if not v["supplementary"]):reviews[1].append("duplicate original/control")
    if set(omitted)!={r["item_id"] for r in status.get("excluded_j2",[]) if r.get("c_assessment")=="미확인·자료 부족"}:
        reviews[1].append("omitted original must retain insufficient-evidence assessment")
    ids=[r["evidence_id"] for r in pkt["issuer_evidence"]]
    for c in pkt["candidates"]:
        candidate=link[c["candidate_id"]]
        document=record["candidate_documents"][candidate["ticker"]]
        for field,locators in reviewed_business().get(document.get("receipt"),{}).items():
            if field not in ("business","financials"):continue
            checked=[curated_fact(document,hint,field=="financials") for hint in locators]
            sent=[sources[v["evidence_id"]] for v in c[field]]
            for expected,actual in zip(checked,sent):
                fields=("quote","location","sha256","table_headers")
                if any(expected.get(k)!=actual.get(k) for k in fields):
                    reviews[1].append(c["candidate_id"]+" manually reviewed "+field+" does not match wire")
            if len(checked)!=len(sent):reviews[1].append(c["candidate_id"]+" reviewed excerpt count mismatch")
        if not c["business"] or c["multiples"] or max(len(c["business"]),len(c["financials"]))>2:
            reviews[1].append(c["candidate_id"]+" content fields/count invalid")
        for fact in c["business"]+c["financials"]:
            ids.append(fact["evidence_id"])
            if len(fact["text"])>350:reviews[1].append(fact["evidence_id"]+" exceeds 350 chars")
    if sorted(ids)!=sorted(sources):reviews[1].append("duplicate or missing evidence IDs")
    path=folder/"c.json"
    if status["ready"]:
        if not path.exists() or read(path)!=pkt:reviews[2].append("actual wire file missing/different")
        else:
            load_packet(path,file_hash(path))
            if sum(l["supplementary"] for l in link.values())!=1:reviews[2].append("supplementary count invalid")
    elif path.exists():reviews[2].append("unready stale wire file present")
    for fact in pkt["issuer_evidence"]+[v for c in pkt["candidates"] for v in c["business"]+c["financials"]]:
        if fact["text"]!=sources[fact["evidence_id"]]["masked_excerpt"]:reviews[2].append("wire mapping drift")
        if re.search(r"https?://|\b\d{14}\b|희망\s*공모가|접수번호|최종\s*(선정|비교)",fact["text"]):
            reviews[2].append(fact["evidence_id"]+" forbidden metadata")
    return {"receipt":receipt,"prepared":status["ready"],"candidate_count":len(link),"evidence_count":len(ids),
            "source_replay":reviews[0],"design_logic":reviews[1],"wire_replay":reviews[2],
            "wire_sha256":file_hash(path) if path.exists() else None,
            "withheld_reasons":status["reasons"]}


def main():
    rows=[verify(r) for r in read(ROSTER)["rows"]]
    failed=sum(any(r[k] for k in ("source_replay","design_logic","wire_replay")) for r in rows)
    dump(BASE/"c_three_reviews.json",{"rounds":["source hashes, cutoff and quoted source bytes",
         "J2 accounting, hash order, eligible evidence fields","actual wire schema, IDs, masking and withheld evidence"],
         "issuers":len(rows),"issuers_with_findings":failed,"rows":rows})
    print("C review findings in", failed, "of", len(rows), "issuers")


if __name__=="__main__":
    main()
