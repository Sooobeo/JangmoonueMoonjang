"""Audit frozen C evidence and prospective exact-string redactions without model outputs."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_main/v1"
DEST = BASE / "corrections/c_blind_names"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"
PAUSE = BASE / "terra/operator_pause_blind_identifiers.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def evidence(packet):
    assert set(packet) == {"issuer_evidence", "candidates"}
    for item in packet["issuer_evidence"]:
        yield "issuer", "issuer_evidence", item
    for candidate in packet["candidates"]:
        assert set(candidate) == {"candidate_id", "business", "financials", "multiples"}
        assert re.fullmatch(r"C[1-9]\d*", candidate["candidate_id"])
        assert candidate["multiples"] == []
        for field in ("business", "financials"):
            for item in candidate[field]:
                yield candidate["candidate_id"], field, item


def matches(rule, text, eid, case):
    if rule["case"] != "*" and case not in rule["case"].split("|"):
        return False
    if "evidence_ids" in rule and eid not in rule["evidence_ids"]:
        return False
    return rule["literal"] in text


def main():
    aliases = read(DEST / "aliases.json")
    frozen = read(BASE / "freeze.json")["files"]
    pause = read(PAUSE)["reservations"]
    assert len(pause) == 45
    sent = {line[1] for line in pause if line[2] == "C"}
    rows, replacements, findings, cards = [], {}, [], []
    scan_matches = {}
    metadata = {}
    market_names = read(BASE / "c_source/kind_names.json")["rows"]
    market_checks = []
    for entry in read(ROSTER)["rows"]:
        case = entry["receipt"]
        path = BASE / "issuers" / case / "c.json"
        was_sent = case in sent
        row = {"case": case, "issuer": entry["issuer"], "sent_before_pause": was_sent}
        rows.append(row)
        if not path.is_file():
            assert not was_sent
            row.update(version="no_C_preparation", direct_self_or_issuer=None,
                       direct_third_party=None, indirect_only_or_also=None)
            continue
        private_path = path.with_name("c_private.json")
        for input_path in (path, private_path):
            assert frozen[input_path.relative_to(ROOT).as_posix()] == digest(input_path)
        original, private = read(path), read(private_path)
        assert original == private["draft"]
        identifiers = {entry["corp_code"], case}
        for linked in private["links"].values():
            identifiers.add(linked["ticker"])
            if linked["item_id"]:
                identifiers.add(linked["item_id"])
        foreign = read(BASE / "c_source/foreign.json").get(case, {})
        for name, foreign_source in foreign.items():
            identifiers.add(foreign_source["receipt"])
        id_re = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(
            re.escape(s) for s in sorted(identifiers) if s) + r")(?![A-Za-z0-9])")
        case_hits = set()
        per_eid = {}
        per_card = {}
        for owner, field, item in evidence(original):
            eid, text = item["evidence_id"], item["text"]
            assert set(item) == {"evidence_id", "text"} and re.fullmatch(r"E[1-9]\d*", eid)
            assert eid not in per_eid
            assert not re.search(r"(?:https?://|www\.|(?<!\d)20\d{12}(?!\d))", text, re.I)
            assert not id_re.search(text)
            compact = re.sub(r"\s+", "", text.casefold())
            for name in market_names:
                if len(name) >= 2 and name in compact:
                    pos = compact.index(name)
                    market_checks.append((case, eid, name, compact[max(0, pos - 12):pos + len(name) + 12]))
            per_eid[eid] = []
            src = private["sources"][eid]
            card_id = case + "/" + owner
            per_card.setdefault(owner, []).append(eid)
            assert src["masked_excerpt"] == text or text.endswith(src["masked_excerpt"])
            for rule in aliases:
                if not matches(rule, text, eid, case):
                    continue
                word, kind = rule["literal"], rule["kind"]
                case_hits.add(kind)
                j = text.index(word)
                findings.append({
                    "case": case, "owner": owner, "field": field, "evidence_id": eid,
                    "kind": kind, "literal": word, "occurrences": text.count(word),
                    "context": text[max(0, j - 25):j + len(word) + 25], "reason": rule["reason"],
                    "corroboration": rule.get("corroboration"), "source": {
                        k: v for k, v in src.items() if k in {
                            "sha256", "source_sha256", "receipt", "published", "url", "location",
                            "physical_page", "page", "row", "row_index", "section", "document",
                            "snapshot", "snapshot_sha256", "section_order", "section_heading_quote",
                        }
                    }, "private_pointer": f"issuers/{case}/c_private.json#/sources/{eid}",
                })
                scan_matches.setdefault(word, []).append(f"{case}/{eid}")
                if kind in ("self", "third"):
                    per_eid[eid].append({"literal": word, "replacement": "[기업]"})
            signature = hashlib.sha256(text.encode("utf-8")).hexdigest()
            metadata.setdefault(card_id, {})[eid] = signature
        for owner, eids in per_card.items():
            cards.append({"case": case, "owner": owner, "reviewed_evidence": eids,
                          "original_text_sha256": metadata[case + "/" + owner]})
        patch = {key: sorted(value, key=lambda x: -len(x["literal"])) for key, value in per_eid.items() if value}
        for _, _, item in evidence(original):
            text = item["text"]
            local_rules = patch.get(item["evidence_id"], [])
            if not was_sent and local_rules:
                predicted = len(text) + sum(
                    text.count(op["literal"]) * (len(op["replacement"]) - len(op["literal"]))
                    for op in local_rules
                )
                if predicted > 350:
                    for op in local_rules:
                        op["replacement"] = "○○"
            for op in local_rules:
                assert op["literal"] in text
                text = text.replace(op["literal"], op["replacement"])
            for op in local_rules:
                assert op["literal"] not in text
            if not was_sent:
                assert len(text) <= 350
            # Legal names may themselves contain digits. Outside the exact
            # replaced spans, every original character including numbers is identical.
            words = [re.escape(op["literal"]) for op in local_rules]
            if words:
                neutral = {op["literal"]: op["replacement"] for op in local_rules}
                assert text == re.sub("|".join(words), lambda m: neutral[m.group()], item["text"])
        if patch:
            replacements[case] = patch
        flags = {"direct_self_or_issuer": "self" in case_hits,
                 "direct_third_party": "third" in case_hits,
                 "indirect_only_or_also": "indirect" in case_hits}
        row.update(version="sent_original" if was_sent else "pending_prospective",
                   original_sha256=digest(path), original_flags=flags,
                   prospective_flags={**flags, "direct_self_or_issuer": False, "direct_third_party": False},
                   n_evidence=len(per_eid), n_cards=len(per_card), **{
                       k: v if was_sent else None for k, v in flags.items()})
    missing = [a for a in aliases if a["kind"] != "indirect" and a["literal"] not in scan_matches]
    assert not missing, missing
    assert len(rows) == 37 and sum(row.get("n_evidence", 0) > 0 for row in rows) == 36
    write(DEST / "replacements.json", replacements)
    write(DEST / "audit.json", {
        "stage": "45-reservation pause, pre-ranking. No response or grading fields read",
        "decision_rule_sha256": digest(BASE / "corrections/c_identity/판단규칙.md"),
        "before_pause_reservations_sha256": digest(PAUSE), "n_distinct_C_before_pause": len(sent),
        "replacements_sha256": digest(DEST / "replacements.json"),
        "aliases_sha256": digest(DEST / "aliases.json"), "source_script_sha256": digest(Path(__file__)),
        "independent_name_scan": {
            "historical_market_source_sha256": digest(BASE / "c_source/kind_names.json"),
            "n_market_aliases": len(market_names),
            "casefolded_ignoring_spaces_matches": market_checks,
            "review": "Scanned all Korean market names at length 2 or greater, not just the corresponding candidate's name. Reviewed contexts include false-positive overlaps in generic words (e.g. 한네트 in 필요한 네트워크) and biomedical or engineering terms; confirmed company hits are in findings. Cross-checked each packet's own domestic and foreign tickers/receipts and original item IDs.",
        },
        "actual_version_rule": "Original flags are factual for pre-pause transmissions. Pending cases have null actual flags; resolve using the exact later wire hash from correction operator manifest and ledger.",
        "indirect_scope": "Recorded concrete named clues and distinctive products, people and organisations. Even with no named clue, exact financials and original business facts may permit reidentification.",
        "reviews": [
            "Every packet and private source matched the original freeze SHA-256. All issuer and candidate fields were enumerated, every excerpt linked to its source and no attachment-bearing fields were present.",
            "Manual review of Hangul, English, Japanese and Chinese names, corporate terms, product brands, report context, short names and false-positive homonyms. Per-excerpt source pointers and decisions recorded.",
            "Exact-string edits independently recomputed from original source strings. Every differing character is confined to a confirmed entity span, with no change to business facts, numbers outside entity spans, ordering, IDs or already transmitted originals.",
        ], "rows": rows, "cards": cards, "findings": findings})
    print(f"{len(rows)} roster / {len(cards)} cards / {sum(r.get('n_evidence', 0) for r in rows)} evidence / {len(sent)} sent / {len(replacements)} packets with direct identifiers")


if __name__ == "__main__":
    main()
