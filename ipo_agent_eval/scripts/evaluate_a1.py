"""Post-ranking, offline natural-issue evaluation. Run from ipo_agent_eval.

python -m scripts.evaluate_a1 MANIFEST.json
python -m scripts.evaluate_a1 --example
Paths are relative to the roster manifest. Human grades must cover ALL original
items. The ranking engine never receives this manifest or the grading files.
Each observed issuer needs observed_runs with ranking_input, a0_batch and
b1_dir. Record each assigned trial and its A0 form in a0_trials.
Add b2_dir if using a valid B2 diagnostic. Archived LIVE failures or
missing-key attempts may justify fallback. Missing evidence keeps an issuer in
the roster as UNEVALUABLE. See --example for the two manifest shapes.
"""

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from ipo_eval.a1_ranking import display
from scripts.a1_observed_runs import OBSERVED_RUNS_SCHEMA, verify_observed

GRADES = {"acceptable", "nonmaterial", "material", "deferred"}
KOREAN_GRADES = {"수용 가능": "acceptable", "비중대 쟁점": "nonmaterial",
                 "중대 쟁점": "material", "판정 유보": "deferred"}


def unique_fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON key")
    return result


def read(path):
    contents = path.read_bytes()
    return json.loads(contents, object_pairs_hook=unique_fields), hashlib.sha256(contents).hexdigest()


def identifiers(values, label):
    if (not isinstance(values, list) or any(not isinstance(i, str) or not i.strip() for i in values)
            or len(values) != len(set(values))):
        raise ValueError(f"invalid or duplicated {label}")
    return set(values)


def grade_case(case_id, ranking, rubric):
    if ranking["case_id"] != case_id or rubric["case_id"] != case_id:
        raise ValueError("issuer identity mismatch")
    if rubric["population"] != "unmodified_original" or rubric["assignment_ref"] != ranking["assignment_ref"]:
        raise ValueError("original population or frozen assignment mismatch")
    if not isinstance(rubric["items"], list) or not isinstance(ranking["items"], list):
        raise TypeError("items must be in a list")
    registered = identifiers([r["id"] for r in ranking["items"]], "original items")
    covered = identifiers([r["id"] for r in rubric["items"]], "rubric items")
    if not registered or registered != covered:
        raise ValueError(f"rubric coverage differs: missing {sorted(registered-covered)}, extra {sorted(covered-registered)}")
    grades = {}
    for item in rubric["items"]:
        grade = KOREAN_GRADES.get(item["grade"], item["grade"])
        if (grade not in GRADES
                or any(not isinstance(item[field], str) or not item[field].strip()
                       for field in ("source_ref", "reason"))):
            raise ValueError(f"{item['id']}: invalid grade, missing evidence or rationale")
        grades[item["id"]] = grade
    primary = ranking["B1"]
    common = identifiers(primary["mandatory"], "common mandatory items")
    basic = identifiers(primary["baseline_extra"], "baseline additional items")
    canary = identifiers(primary["canary_extra"], "canary additional items")
    if not (common | basic | canary) <= registered or common & (basic | canary):
        raise ValueError("review lists overlap mandatory items or contain unregistered items")
    k = ranking["k"]
    if type(k) is not int or k < 0 or len(basic) != len(canary) or len(canary) != min(k, len(registered-common)):
        raise ValueError("review lists do not use the registered equal additional budget")
    material = {i for i, grade in grades.items() if grade == "material"}
    deferred = {i for i, grade in grades.items() if grade == "deferred"}
    outside_basic = registered - common - basic
    outside_canary = registered - common - canary
    entered = canary - basic
    displaced = basic - canary
    delta = len(outside_basic & material) - len(outside_canary & material)
    return {
        "status": "EVALUABLE", "original_status": ranking["status"],
        "registered_items": len(registered), "material": len(material), "deferred": len(deferred),
        "mandatory": len(common), "extra_per_list": len(basic),
        "baseline_missed": sorted(outside_basic & material), "canary_missed": sorted(outside_canary & material),
        "baseline_outside_deferred": sorted(outside_basic & deferred),
        "canary_outside_deferred": sorted(outside_canary & deferred),
        "entered": sorted(entered), "displaced": sorted(displaced),
        "entered_material": sorted(entered & material), "displaced_material": sorted(displaced & material),
        "entered_deferred": sorted(entered & deferred), "displaced_deferred": sorted(displaced & deferred),
        "delta": delta, "lower": delta - len(displaced & deferred), "upper": delta + len(entered & deferred),
    }


def aggregate(rows):
    valid = [r for r in rows if r["status"] == "EVALUABLE"]
    n = len(valid)
    means = {field: Fraction(sum(r[field] for r in valid), n) if n else None
             for field in ("delta", "lower", "upper")}
    denominator = sum(r["material"] for r in valid)
    basic = sum(len(r["baseline_missed"]) for r in valid)
    canary = sum(len(r["canary_missed"]) for r in valid)
    return {
        "selected_issuers": len(rows), "evaluated_issuers": n, "unevaluable_issuers": len(rows) - n,
        "improved": sum(r["delta"] > 0 for r in valid), "worsened": sum(r["delta"] < 0 for r in valid),
        "tied": sum(r["delta"] == 0 for r in valid),
        "equal_issuer_mean_delta": display(means["delta"]), "mean_lower": display(means["lower"]),
        "mean_upper": display(means["upper"]),
        "deferred_bounds_include_zero": means["lower"] <= 0 <= means["upper"] if n else None,
        "material_issues": denominator, "baseline_missed": basic, "canary_missed": canary,
        "baseline_missed_rate": display(Fraction(basic, denominator)) if denominator else None,
        "canary_missed_rate": display(Fraction(canary, denominator)) if denominator else None,
        "issuers_with_replacement": sum(bool(r["entered"]) for r in valid),
    }


def evaluate(manifest_path):
    manifest, digest = read(manifest_path)
    if manifest["population"] != "unmodified_original" or manifest["data_kind"] not in {"synthetic", "observed"}:
        raise ValueError("specify the unmodified original population and data_kind synthetic/observed")
    roster = manifest["issuers"]
    if not roster or not isinstance(roster, list):
        raise ValueError("supply a nonempty preselected issuer roster")
    identifiers([r["case_id"] for r in roster], "preselected issuers")
    rows = []
    for entry in roster:
        row = {"case_id": entry["case_id"]}
        if "unavailable_reason" in entry:
            if not isinstance(entry["unavailable_reason"], str) or not entry["unavailable_reason"].strip():
                raise ValueError(f"{entry['case_id']}: provide a nonempty exclusion reason")
            if "ranking" in entry or "rubric" in entry:
                raise ValueError(f"{entry['case_id']}: competing evaluation and exclusion records")
            row.update(status="UNEVALUABLE", reason=entry["unavailable_reason"])
        else:
            try:
                ranking, row["ranking_sha256"] = read(manifest_path.parent / entry["ranking"])
                rubric, row["rubric_sha256"] = read(manifest_path.parent / entry["rubric"])
                for field in ("ranking_sha256", "rubric_sha256"):
                    if field in entry and entry[field] != row[field]:
                        raise ValueError(f"{field} differs from the registered digest")
                if manifest["data_kind"] == "observed":
                    row["observed_runs"] = verify_observed(manifest_path.parent, entry, ranking)
                row.update(grade_case(entry["case_id"], ranking, rubric))
            except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
                row.update(status="UNEVALUABLE", reason=str(exc))
        rows.append(row)
    return {"data_kind": manifest["data_kind"], "population": manifest["population"],
            "manifest_sha256": digest, "issuers": rows, "summary": aggregate(rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("manifest", type=Path, nargs="?")
    group.add_argument("--example", action="store_true",
                       help="Print an example roster and separate synthetic human-grade input")
    group.add_argument("--observed-runs-schema", action="store_true",
                       help="Print the per-issuer JSON schema for archived LIVE evidence")
    args = parser.parse_args(argv)
    if args.observed_runs_schema:
        output = OBSERVED_RUNS_SCHEMA
    elif args.example:
        common = {"population": "unmodified_original"}
        output = {
            "manifest": {**common, "data_kind": "synthetic", "issuers": [
                {"case_id": "SYNTHETIC", "ranking": "ranking.json", "rubric": "rubric.json"}]},
            "observed_manifest_template": {**common, "data_kind": "observed", "issuers": [
                {"case_id": "<issuer-id>", "ranking": "ranking.json", "rubric": "rubric.json",
                 "observed_runs": {"ranking_input": "annotations.json", "a0_batch": "prepared-a0",
                                   "b1_dir": "runs/<B1-run-id>",
                                   "a0_trials": [{"trial_id": "<canary-trial-id>", "role": "canary",
                                                  "quote": "<passage from the submitted review>"},
                                                 {"trial_id": "<control-trial-id>", "role": "control",
                                                  "quote": None}]}}]},
            "rubric": {**common, "case_id": "SYNTHETIC", "assignment_ref": "synthetic-v1",
                       "items": [{"id": item, "grade": grade, "source_ref": "synthetic p.1",
                                  "reason": "synthetic example"} for item, grade in
                                 (("X", "material"), ("Y", "material"), ("W", "deferred"))]},
        }
    else:
        try:
            output = evaluate(args.manifest)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            parser.exit(2, f"{parser.prog}: {exc}\n")
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
