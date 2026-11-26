"""Present A0 and C claims against frozen originals and seal separately reviewed findings."""

import argparse
import hashlib
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_main/v1"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lock(path, record):
    raw = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Immutable source review differs: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(raw)


def context(source, quote, side):
    # Ignore whitespace for matching but keep original characters around the located row.
    positions = [i for i, ch in enumerate(source) if not ch.isspace()]
    body = "".join(source[i] for i in positions)
    text = "".join(quote.split())
    start = body.find(text)
    if not text or start < 0:
        return {"exact": False, "occurrences": 0, "surrounding": ""}
    a, b = positions[start], positions[start + len(text) - 1] + 1
    return {
        "exact": True,
        "occurrences": body.count(text),
        "surrounding": " ".join(source[max(a - side, 0) : b + side].split()),
    }


def inspect(case, side=210, base=BASE, roster=ROSTER):
    issuer = base / "issuers" / case
    roles = base / "terra" / case
    record = next(r for r in read(roster)["rows"] if r["receipt"] == case)
    source = roster.parent / record["pdf_file"]
    if sha(source.read_bytes()) != record["pdf_sha256"]:
        raise ValueError("Original filing digest mismatch")
    items = read(issuer / "items.json")
    a0_path, c_path = roles / "A0.json", roles / "C.json"
    a0 = read(a0_path)["answer"]["items"] if a0_path.exists() else []
    c = read(c_path)["answer"] if c_path.exists() else None
    c_packet = read(issuer / "c.json") if c is not None else None
    private = read(issuer / "c_private.json") if c is not None else {}
    by_id = {r["item_id"]: r for r in a0}
    submitted = read(issuer / "a0.json")["original_physical_pages"] if a0 else {}
    if a0 and (len(by_id) != len(a0) or set(by_id) != {i["id"] for i in items}):
        raise ValueError("A0 item population mismatch")
    cs = {}
    sources = {}
    if c is not None:
        original = {
            v["item_id"]: k for k, v in private["links"].items() if v.get("item_id")
        }
        decisions = {r["candidate_id"]: r for r in c["candidates"]}
        sources.update(
            {r["evidence_id"]: r["text"] for r in c_packet["issuer_evidence"]}
        )
        issuer_refs = set(sources)
        for cand in c_packet["candidates"]:
            rows = cand["business"] + cand["financials"]
            sources.update({r["evidence_id"]: r["text"] for r in rows})
        for n, item in enumerate(items):
            key = item["id"]
            if n < 2:
                proposal = c["methods"][("period", "attribution")[n]]
                own = issuer_refs
            elif key in original:
                cid = original[key]
                proposal = decisions[cid]
                cand = next(
                    r for r in c_packet["candidates"] if r["candidate_id"] == cid
                )
                own = {r["evidence_id"] for r in cand["business"] + cand["financials"]}
            else:
                continue
            cs[key] = {
                "proposal": proposal,
                "registered": all(e in sources for e in proposal["evidence_ids"]),
                "own_evidence": bool(set(proposal["evidence_ids"]) & own),
                "cited": {e: sources.get(e) for e in proposal["evidence_ids"]},
                "private_mapping_matches": all(
                    private["sources"].get(e, {}).get("masked_excerpt")
                    == sources.get(e)
                    and e in sources
                    for e in proposal["evidence_ids"]
                ),
                "source_context": {
                    e: {
                        k: private["sources"].get(e, {}).get(k)
                        for k in (
                            "quote",
                            "period",
                            "physical_page",
                            "location",
                            "published",
                            "sha256",
                        )
                    }
                    for e in proposal["evidence_ids"]
                },
            }
    entries = {}
    with fitz.open(source) as pdf:
        for item in items:
            key = item["id"]
            evidence = [
                {"page": r["page"], "quote": " ".join(r["quote"].split())}
                for r in item["evidence"]
            ]
            line = {
                "question": item["question"],
                "target": item["target"],
                "family": item["family"],
                "original_category": item.get("original_category"),
                "original_choice": item.get("original_choice"),
                "source_rows": evidence,
                "A0": None,
                "C": cs.get(key),
            }
            if key in by_id:
                claim = by_id[key]
                p = claim["physical_page"]
                text = pdf[p - 1].get_text(sort=True)
                line["A0"] = {
                    "page": p,
                    "state": claim["state"],
                    "quote": claim["quote"],
                    "reason": claim["reason"],
                    "belongs_to_item": p in item["pages"],
                    "input_matches_filing": submitted.get(str(p)) == text,
                    **context(text, claim["quote"], side),
                }
            entries[key] = line
    return {
        "case": case,
        "original_pdf_sha256": record["pdf_sha256"],
        "A0_sha256": sha(a0_path.read_bytes()) if a0_path.exists() else None,
        "C_sha256": sha(c_path.read_bytes()) if c_path.exists() else None,
        "items": entries,
    }


def seal(case, findings):
    role_dir = BASE / "terra" / case
    view = inspect(case)
    for name in ("A0", "C"):
        need = {key for key, r in view["items"].items() if r[name] is not None}
        records = findings[name]
        if set(records) != need:
            raise ValueError(
                f"{case} {name} finding population disagrees with submitted claims"
            )
        for key, finding in records.items():
            claim = view["items"][key][name]
            if (
                finding["status"]
                not in {"verified", "conditional", "insufficient", "citation_mismatch"}
                or not finding["reason"].strip()
            ):
                raise ValueError(f"Missing semantic finding for {key}")
            exact = (
                (
                    claim["exact"]
                    and claim["belongs_to_item"]
                    and claim["input_matches_filing"]
                )
                if name == "A0"
                else (
                    claim["registered"]
                    and claim["own_evidence"]
                    and claim["private_mapping_matches"]
                )
            )
            if not exact and finding["status"] == "verified":
                raise ValueError(
                    f"Unverified original or missing own citation for {key}"
                )
    summary = {
        "case": case,
        "original_pdf_sha256": view["original_pdf_sha256"],
        "A0_sha256": view["A0_sha256"],
        "C_sha256": view["C_sha256"],
        "reviews": {
            "1_population": {
                "original_items": len(view["items"]),
                "submitted_A0": len(findings["A0"]),
                "comparable_C": len(findings["C"]),
            },
            "2_source": {
                key: {
                    "A0": {
                        k: row["A0"][k]
                        for k in (
                            "page",
                            "exact",
                            "belongs_to_item",
                            "input_matches_filing",
                            "occurrences",
                        )
                    }
                    if row["A0"]
                    else None,
                    "C": {
                        k: row["C"][k]
                        for k in (
                            "registered",
                            "own_evidence",
                            "private_mapping_matches",
                        )
                    }
                    if row["C"]
                    else None,
                }
                for key, row in view["items"].items()
            },
            "3_semantic": findings,
        },
    }
    lock(BASE / "role_source_review" / (case + ".json"), summary)
    template = role_dir / "audit_template.json"
    if template.exists():
        t = read(template)
        if set(t["records"]) != set(findings["C"]) or t["roles_sha256"] != sha(
            (role_dir / "roles.json").read_bytes()
        ):
            raise ValueError("Paired C audit does not match the frozen roles")
        lock(
            role_dir / "role_audit.json",
            {"roles_sha256": t["roles_sha256"], "records": findings["C"]},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("--side", type=int, default=210)
    parser.add_argument("--item")
    parser.add_argument("--findings", type=Path)
    args = parser.parse_args()
    if args.findings:
        seal(args.case, read(args.findings))
    else:
        view = inspect(args.case, args.side)
        if args.item:
            view = view["items"][args.item]
        print(json.dumps(view, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
