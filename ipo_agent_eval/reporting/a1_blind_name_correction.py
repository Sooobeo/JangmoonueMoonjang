"""Apply the prospectively recorded name redactions to unexposed C packets only."""

import argparse
import contextlib
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from reporting import a1_role_source_review as review
from scripts import a1_main_terra as terra

BASE = terra.BASE
DIRECTORY = BASE / "corrections/c_blind_names"
BOUNDARY = BASE / "terra/operator_pause_blind_identifiers.json"
FREEZE = BASE / "freeze.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def canonical(obj):
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def rows(packet):
    return {
        r["evidence_id"]: r
        for r in [
            *packet["issuer_evidence"],
            *(
                r
                for c in packet["candidates"]
                for field in ("business", "financials")
                for r in c[field]
            ),
        ]
    }


def substitute(packet, private, changes):
    packet, private = copy.deepcopy(packet), copy.deepcopy(private)
    sources = rows(packet)
    issuer_ids = {r["evidence_id"] for r in packet["issuer_evidence"]}
    for eid, entries in changes.items():
        visible = sources[eid]
        origin = private["sources"][eid]
        if origin["masked_excerpt"] != visible["text"]:
            raise ValueError(
                "Original source mapping disagrees with presented text: " + eid
            )
        text = visible["text"]
        standard = text
        for mapping in entries:
            standard = standard.replace(mapping["literal"], "[기업]")
        required_marker = (
            "○○" if eid not in issuer_ids and len(standard) > 350 else "[기업]"
        )
        for mapping in entries:
            literal, new = mapping["literal"], mapping["replacement"]
            if (
                not literal
                or literal not in text
                or new != required_marker
                or literal == new
            ):
                raise ValueError("Invalid exact-name substitution: " + eid)
            text = text.replace(literal, new)
            origin["redactions"][literal] = new
        if len(text) > 350 and eid not in issuer_ids:
            raise ValueError("Candidate excerpt over cap after redaction: " + eid)
        visible["text"] = origin["masked_excerpt"] = text
    return packet, private


def boundary():
    saved = read(BOUNDARY)
    admission = saved["reservations"]
    if len(admission) != 45 or [r[0] for r in admission] != list(range(1, 46)):
        raise ValueError("Unexpected recorded stop boundary")
    path = BASE / "terra/ledger.sqlite3"
    with contextlib.closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        actual = db.execute(
            "SELECT id,receipt,stage,kind FROM attempt WHERE id<=45 ORDER BY id"
        ).fetchall()
    if [list(r) for r in actual] != [r[:4] for r in admission]:
        raise ValueError(
            "Captured admission boundary disagrees with the original Terra ledger"
        )
    return {receipt for _, receipt, stage, _ in actual if stage == "C"}


def prepare():
    manifest_file = DIRECTORY / "manifest.json"
    if manifest_file.exists():
        verified()
        return read(manifest_file)
    source = read(DIRECTORY / "replacements.json")
    identity = read(DIRECTORY / "audit.json")
    audited = {row["case"]: row for row in identity["rows"]}
    artifacts = {
        "decision_rule_sha256": BASE / "corrections/c_identity/판단규칙.md",
        "before_pause_reservations_sha256": BOUNDARY,
        "aliases_sha256": DIRECTORY / "aliases.json",
        "replacements_sha256": DIRECTORY / "replacements.json",
    }
    if any(identity[key] != sha(path.read_bytes()) for key, path in artifacts.items()):
        raise ValueError("Identity audit and reviewed correction artifacts disagree")
    fsha, receipts, decision, files = terra.load_freeze(FREEZE)
    already_sent = boundary()
    if not set(source).issubset(receipts) or set(audited) != set(receipts):
        raise ValueError("Issuer population mismatch in name correction")
    path = BASE / "terra/ledger.sqlite3"
    with contextlib.closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        if db.execute("SELECT COUNT(*) FROM attempt").fetchone()[0] != 45:
            raise ValueError("New admissions after the stop, before the amendment")
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='operator_pause_admission'"
        ).fetchone():
            raise ValueError(
                "New admissions must be paused when the version is registered"
            )
    entries = {}
    for case in receipts:
        if not decision[case]["c_ready"]:
            if case in source:
                raise ValueError("No dispatchable original C packet: " + case)
            continue
        data = terra.load_inputs(case, files, ("items", "c", "c_private", "c_status"))
        changes = source.get(case, {})
        apply = bool(changes) and case not in already_sent
        row = audited[case]
        if (
            row["original_sha256"]
            != sha((BASE / "issuers" / case / "c.json").read_bytes())
            or row["sent_before_pause"] != (case in already_sent)
            or bool(changes)
            != (
                row["original_flags"]["direct_self_or_issuer"]
                or row["original_flags"]["direct_third_party"]
            )
        ):
            raise ValueError(
                "Source version or exposure disagrees with identity audit: " + case
            )
        pub, priv = (
            substitute(data["c"], data["c_private"], changes)
            if apply
            else (data["c"], data["c_private"])
        )
        terra.check_inputs(case, {**data, "c": pub, "c_private": priv})
        entries[case] = {
            "prior_C_admission": case in already_sent,
            "direct_identifiers_found": bool(changes),
            "apply_prospectively": apply,
            "effective_flags": row["prospective_flags"]
            if apply
            else row["original_flags"],
            "evidence_ids": sorted(changes),
            "original_C_sha256": sha(canonical(data["c"])),
            "effective_C_sha256": sha(canonical(pub)),
            "original_private_sha256": sha(canonical(data["c_private"])),
            "effective_private_sha256": sha(canonical(priv)),
        }
    record = {
        "protocol": "a1-main-v1",
        "freeze_sha256": fsha,
        "boundary_sha256": sha(BOUNDARY.read_bytes()),
        "replacement_sha256": sha((DIRECTORY / "replacements.json").read_bytes()),
        "identity_audit_sha256": sha((DIRECTORY / "audit.json").read_bytes()),
        "correction_policy_sha256": sha(
            (BASE / "corrections/c_identity/판단규칙.md").read_bytes()
        ),
        "correction_runtime_sha256": sha(Path(__file__).read_bytes()),
        "records": entries,
        "applied": [c for c, e in entries.items() if e["apply_prospectively"]],
        "already_exposed_with_identifiers": [
            c
            for c, e in entries.items()
            if e["prior_C_admission"] and e["direct_identifiers_found"]
        ],
    }
    review.lock(manifest_file, record)
    checksum = DIRECTORY / "manifest.sha256"
    with checksum.open("x", encoding="ascii") as f:
        f.write(sha(manifest_file.read_bytes()) + "\n")
    return record


def verified():
    file = DIRECTORY / "manifest.json"
    record = read(file)
    facts = {
        "freeze_sha256": sha(FREEZE.read_bytes()),
        "boundary_sha256": sha(BOUNDARY.read_bytes()),
        "replacement_sha256": sha((DIRECTORY / "replacements.json").read_bytes()),
        "identity_audit_sha256": sha((DIRECTORY / "audit.json").read_bytes()),
        "correction_policy_sha256": sha(
            (BASE / "corrections/c_identity/판단규칙.md").read_bytes()
        ),
        "correction_runtime_sha256": sha(Path(__file__).read_bytes()),
    }
    if sha(file.read_bytes()) != (
        DIRECTORY / "manifest.sha256"
    ).read_text().strip() or any(record[k] != v for k, v in facts.items()):
        raise ValueError("Name-correction binding changed")
    previous = boundary()
    if {
        c for c, e in record["records"].items() if e["prior_C_admission"]
    } != previous or previous.intersection(record["applied"]):
        raise ValueError(
            "Name correction would alter a previously transmitted C request"
        )
    return record, read(DIRECTORY / "replacements.json")


def checked_pair(case, record, changes):
    folder = BASE / "issuers" / case
    original = read(folder / "c.json")
    private = read(folder / "c_private.json")
    expected = record["records"][case]
    if (
        sha(canonical(original)) != expected["original_C_sha256"]
        or sha(canonical(private)) != expected["original_private_sha256"]
    ):
        raise ValueError("Original C/source changed for " + case)
    effective = (
        substitute(original, private, changes[case])
        if expected["apply_prospectively"]
        else (original, private)
    )
    if (
        sha(canonical(effective[0])) != expected["effective_C_sha256"]
        or sha(canonical(effective[1])) != expected["effective_private_sha256"]
    ):
        raise ValueError("Effective C/source changed for " + case)
    return effective


@contextlib.contextmanager
def effective_inputs():
    record, changes = verified()
    original_load, original_review = terra.load_inputs, review.read

    def terra_load(case, files, keys=terra.REQUIRED):
        data = original_load(case, files, keys)
        if "c" in data:
            data["c"], data["c_private"] = checked_pair(case, record, changes)
        return data

    def reviewer_read(path):
        if (
            path.name in {"c.json", "c_private.json"}
            and path.parent.parent == BASE / "issuers"
            and path.parent.name in record["records"]
        ):
            pair = checked_pair(path.parent.name, record, changes)
            return pair[path.name == "c_private.json"]
        return original_review(path)

    with (
        patch.object(terra, "load_inputs", terra_load),
        patch.object(review, "read", reviewer_read),
    ):
        yield record


def proof(final=False):
    record, changes = verified()
    observed = {}
    actual = {}
    with contextlib.closing(
        sqlite3.connect(
            (BASE / "terra/ledger.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
        )
    ) as db:
        attempts = list(
            db.execute(
                "SELECT id,receipt,stage,kind,request,request_hash FROM attempt WHERE stage IN ('C','A1_SELECT') ORDER BY id"
            )
        )
        responses = {
            n: (raw, digest)
            for n, raw, digest in db.execute(
                "SELECT a.id,o.body,o.body_hash FROM attempt a JOIN outcome o USING(id) WHERE stage='C'"
            )
        }
    for identifier, case, stage, kind, raw, request_sha in attempts:
        if case not in actual:
            actual[case] = checked_pair(case, record, changes)
        packet, mapping = actual[case]
        if sha(raw) != request_sha:
            raise ValueError("Ledger request digest mismatch")
        wire = json.loads(json.loads(raw)["input"])
        if kind == "format_repair" or "prior_submission" in wire:
            wire = wire["input"]
        if stage == "C":
            if wire != packet:
                raise ValueError("Effective packet and actual C wire differ: " + case)
        else:
            for eid, row in rows(packet).items():
                if wire["original_sources"].get(eid) != row["text"]:
                    raise ValueError(f"A1 used a different C source: {case}/{eid}")
        observed.setdefault(case, {"C": [], "A1_SELECT": []})[stage].append(identifier)
    citations = 0
    for case, (packet, mapping) in actual.items():
        folder = BASE / "terra" / case
        if (folder / "C.json").exists():
            submission = read(folder / "C.json")
            attempt = submission["attempt"]
            if attempt not in observed[case]["C"] or attempt not in responses:
                raise ValueError(
                    "C role is not bound to an original HTTP response: " + case
                )
            raw, body_hash = responses[attempt]
            answer = terra.output_json(json.loads(raw))
            if (
                body_hash != sha(raw)
                or body_hash != submission["response_sha256"]
                or answer != submission["answer"]
            ):
                raise ValueError(
                    "C response bytes or submitted answer changed: " + case
                )
            terra.check_c(packet, answer)
            presented = rows(packet)
            for cell in [
                *answer["candidates"],
                *answer["methods"].values(),
                answer["earnings"],
                answer["aggregation"],
            ]:
                for k in cell["evidence_ids"]:
                    if (
                        presented[k]["text"] != mapping["sources"][k]["masked_excerpt"]
                        or not mapping["sources"][k]["quote"]
                    ):
                        raise ValueError(f"Cannot restore cited source: {case}/{k}")
                    citations += 1
        elif final and not (folder / "role_failures.json").exists():
            raise ValueError("Missing terminal C-role evidence: " + case)
    if final and set(actual) != set(record["records"]):
        raise ValueError("Some C-ready issuers did not reach a request")
    result = {
        "scope": "exact original/effective C wire, source mapping and propagation into actual selector input",
        "manifest_sha256": sha((DIRECTORY / "manifest.json").read_bytes()),
        "checked_citations": citations,
        "exposure_by_actual_wire": {
            c: {
                "version": "prospective_redaction"
                if record["records"][c]["apply_prospectively"]
                else "original",
                **record["records"][c]["effective_flags"],
            }
            for c, v in observed.items()
            if v["C"]
        },
        "actual": observed,
    }
    if final:
        review.lock(DIRECTORY / "completed_wire_proof.json", result)
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "command", choices=("prepare", "verify", "run", "view", "seal", "proof")
    )
    cli.add_argument("--case")
    cli.add_argument("--findings", type=Path)
    cli.add_argument("--roles-only", action="store_true")
    cli.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=3)
    cli.add_argument("--final", action="store_true")
    args = cli.parse_args()
    if args.command == "prepare":
        result = prepare()
        print(
            "prospective",
            result["applied"],
            "originals retained",
            result["already_exposed_with_identifiers"],
        )
    elif args.command == "proof":
        print(json.dumps(proof(args.final), ensure_ascii=False))
    else:
        with effective_inputs():
            if args.command == "run":
                terra.main(
                    [
                        "--freeze",
                        str(FREEZE),
                        "--workers",
                        str(args.workers),
                        *(["--roles-only"] if args.roles_only else []),
                    ]
                )
            elif args.command == "verify":
                terra.main(["--freeze", str(FREEZE), "--preflight"])
            elif args.command == "view":
                print(
                    json.dumps(review.inspect(args.case), ensure_ascii=False, indent=2)
                )
            elif args.command == "seal":
                review.seal(args.case, read(args.findings))


if __name__ == "__main__":
    main()
