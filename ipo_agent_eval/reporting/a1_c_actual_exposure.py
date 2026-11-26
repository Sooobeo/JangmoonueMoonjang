"""Join only C request bytes to the pre-ranking name audit for all 37 issuers."""

import contextlib
import json
import sqlite3
import re

from reporting import a1_blind_name_correction as correction
from reporting.a1_c_identity_incident import BASE, DEST, ROSTER, digest, read, write


def residual(manifest, changes):
    """Verify the single post-send discovery against all original/effective packets."""
    hits = []
    words = ("에이프릴스킨", "aprilskin", "april skin")
    for case in manifest["records"]:
        packet, private = correction.checked_pair(case, manifest, changes)
        original = read(BASE / "issuers" / case / "c.json")
        for kind, obj in (("original", original), ("effective", packet)):
            for eid, row in correction.rows(obj).items():
                for word in words:
                    if word in row["text"].casefold():
                        hits.append({"case": case, "version": kind, "evidence_id": eid, "literal": word,
                                     "source": private["sources"][eid]["location"]})
    case = "20250325000608"
    assert {(h["case"], h["version"], h["evidence_id"], h["literal"]) for h in hits} == {
        (case, v, e, "에이프릴스킨") for v in ("original", "effective") for e in ("E14", "E15", "E17")
    }
    issuer = next(r for r in read(ROSTER)["rows"] if r["receipt"] == "20231222000680")
    proof_pdf = ROSTER.parent / issuer["pdf_file"]
    assert digest(proof_pdf) == issuer["pdf_sha256"]
    import fitz
    with fitz.open(proof_pdf) as pdf:
        text = " ".join(pdf[282].get_text().split())
    quote = re.search(r"2014\.12\.09 주식회사 에이프릴스킨 상호변경 2017\.06\.29 주식회사 에이피알 상호변경", text)
    assert quote
    result = {
        "case": case, "candidate": "에이피알", "candidate_id": "C3",
        "classification": "direct_self_or_issuer", "direct_self_or_issuer": True,
        "discovered": "W13 review of the already-returned corrected C role",
        "history": {"source": issuer["pdf_url"], "pdf_sha256": issuer["pdf_sha256"], "physical_page": 283,
                    "quote": quote.group(), "company_history_url": "https://apr-blog.com/apr-youth-employment",
                    "company_history_snapshot_sha256": digest(DEST / "apr_history.html"),
                    "date_precision": "IPO filing records 2017-06-29. Issuer article summarises as July 2017."},
        "review": ["36 frozen packets rechecked for Hangul and English variants",
                   "36 registered effective packets rechecked; only one packet and three evidence rows contained the former name",
                   "Actual outgoing C request independently matched to prospective packet; response already received and original request and response are retained"],
        "matches": hits, "manifest_sha256": digest(DEST / "manifest.json"),
    }
    with contextlib.closing(sqlite3.connect((BASE / "terra/ledger.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        sent = db.execute("SELECT a.id, a.kind, a.request,a.request_hash, o.status FROM attempt a JOIN outcome o USING(id) WHERE a.receipt=? AND a.stage='C' ORDER BY a.id", (case,)).fetchall()
    assert sent
    packet, _ = correction.checked_pair(case, manifest, changes)
    result["observed"] = []
    for num, kind, raw, hash_value, status in sent:
        wire = json.loads(json.loads(raw)["input"])
        if kind == "format_repair" or "prior_submission" in wire:
            wire = wire["input"]
        assert wire == packet and correction.sha(raw) == hash_value and status is not None
        result["observed"].append({"id": num, "request_sha256": hash_value, "http_status": status})
    path = DEST / "residual_name.json"
    if path.exists():
        assert read(path) == result
    else:
        write(path, result)
    return result


def exposure():
    manifest, changes = correction.verified()
    appendix = residual(manifest, changes)
    uri = (BASE / "terra/ledger.sqlite3").resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as ledger:
        attempts = ledger.execute(
            "SELECT a.id,a.receipt,a.kind,a.request,a.request_hash,o.status "
            "FROM attempt a LEFT JOIN outcome o USING(id) WHERE stage='C' ORDER BY a.id"
        ).fetchall()
    by_receipt = {}
    for attempt, case, kind, raw, request_hash, status in attempts:
        assert status is not None, (attempt, "transport receipt pending or delivery uncertain")
        assert correction.sha(raw) == request_hash
        wire = json.loads(json.loads(raw)["input"])
        if kind == "format_repair" or "prior_submission" in wire:
            wire = wire["input"]
        packet, _ = correction.checked_pair(case, manifest, changes)
        assert packet == wire
        by_receipt.setdefault(case, []).append({"id": attempt, "request_sha256": request_hash,
                                               "http_status": status,
                                               "canonical_C_sha256": correction.sha(correction.canonical(wire))})
    rows = []
    for issuer in read(ROSTER)["rows"]:
        case = issuer["receipt"]
        observed = by_receipt.get(case, [])
        record = manifest["records"].get(case)
        if not observed:
            assert not record, (case, "dispatchable case still outstanding")
        flags = (record["effective_flags"] if observed else
                 {"direct_self_or_issuer": False, "direct_third_party": False, "indirect_only_or_also": False})
        if observed and case == appendix["case"]:
            flags = {**flags, appendix["classification"]: True}
        rows.append({
            "case": case, "issuer": issuer["issuer"], "sent": bool(observed),
            "sent_before_pause": bool(record and record["prior_C_admission"]),
            "version": ("not_sent" if not observed else
                        "prospective_redaction" if record["apply_prospectively"] else "original"),
            **flags, "requests": observed,
            "original_file_sha256": digest(BASE / "issuers" / case / "c.json") if record else None,
            "canonical_effective_C_sha256": record["effective_C_sha256"] if observed else None,
        })
    assert len(rows) == 37 and len(by_receipt) == len(manifest["records"])
    result = {"freeze_sha256": manifest["freeze_sha256"],
              "identity_audit_sha256": manifest["identity_audit_sha256"],
              "boundary_sha256": manifest["boundary_sha256"], "manifest_sha256": digest(DEST / "manifest.json"),
              "post_send_identity_appendix_sha256": digest(DEST / "residual_name.json"),
              "method": "All and only C requests were read from the Terra ledger. The response HTTP status, full request SHA-256 and equality of the decoded C payload to its registered effective version were checked for each attempt.",
              "rows": rows}
    target = DEST / "actual_exposure.json"
    if target.is_file():
        assert read(target) == result
    else:
        write(target, result)
    return result


if __name__ == "__main__":
    print(len(exposure()["rows"]), "issuers verified")
