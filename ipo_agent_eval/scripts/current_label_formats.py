"""Compare three input formats using the same isolated, lookup-disabled reviewer."""

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from subprocess import TimeoutExpired

from jsonschema import ValidationError

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import ask, digest, load
from scripts.current_proxy import ask_proxy
from scripts.current_selector import (
    DECISION,
    PROMPT,
    evidence_ids,
    original_inputs,
    rule_table,
    state,
)

OUTPUT = OUT / "formats"
CONDITIONS = ("L1", "L2", "L3")
ROLES = ("a0", "c")
INSTRUCTIONS = PROMPT + """ 이번 실행에는 추가 원문 조회가 없다. 현재 제시된 사전검증과 두 검토자의 전달 내용을 근거로 판단한다. 출처 ID가 제시되어 확인 근거로 삼을 수 있는 경우에만 반환 근거 ID에 넣는다. 판정은 보이지만 인용·사실이 없어 사실을 검증할 수 없는 경우에는 미확인 사유를 적고 인용을 만들지 않는다. 각 항목을 정확히 한 번 평가한다."""
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
RESTRICTED_FIELDS = {"additional_read", "available_pages", "grade", "grades", "rubric", "rubrics", "ground_truth"}


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def bundle(path):
    cases = load(path)["cases"]
    if isinstance(cases, dict):
        return cases
    return {(case.get("case_id") or case["case"]).split("-")[0]: case for case in cases}


def restricted_fields(value):
    if isinstance(value, dict):
        return (RESTRICTED_FIELDS & value.keys()) | set().union(*(restricted_fields(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(restricted_fields(v) for v in value))
    return set()


def source_location(source, local=None):
    if not isinstance(source, dict):
        return ""
    page = source.get("page", source.get("physical_page"))
    section = local or source.get("section")
    return " · ".join(part for part in (f"PDF 물리 {page}쪽" if page else "", section,
                                         source.get("published")) if part)


def role_record(role, sources):
    facts = []
    consumed = set()
    for entry in role.get("evidence", []):
        if not isinstance(entry, dict):
            continue
        for ref in entry.get("source_refs") or entry.get("evidence_refs") or []:
            if ref not in sources:
                continue
            location = next((row.get("locator") for row in entry.get("locations", []) if row["source_ref"] == ref), None)
            item = {"fact": entry["fact"], "direction": entry.get("direction") or "",
                    "source_id": ref, "location": source_location(sources[ref], location)}
            if item not in facts:
                facts.append(item)
            consumed.add(ref)
    for ref in sorted(evidence_ids(role) - consumed):
        if ref not in sources:
            continue
        source = sources[ref]
        snippet = source if isinstance(source, str) else next(
            (source[k] for k in ("excerpt", "text", "quote", "fact") if source.get(k)), "")
        facts.append({"fact": snippet, "direction": "", "source_id": ref, "location": source_location(source)})
    return {"judgment": state(role), "reason": role.get("reason") or "",
            "open_condition": role.get("open_condition") or role.get("limit") or "", "evidence": facts}


def prose(row):
    item = [f"항목 {quote(row['item_id'])}에 관한 검토다."]
    expected = [row["item_id"]]
    for role, name in (("a0", "A0"), ("c", "C")):
        record = row[role]
        verdict, reason, condition = (record[field] for field in ("judgment", "reason", "open_condition"))
        item.append(f"{name}는 {quote(verdict)}로 판단했다. 이유는 {quote(reason)}이다. 남은 확인 사항은 {quote(condition)}이다.")
        expected.extend([verdict, reason, condition])
        for fact in record["evidence"]:
            text, direction, ref, location = (fact[k] for k in ("fact", "direction", "source_id", "location"))
            item.append(f"{name}가 낸 근거 사실은 {quote(text)}이고 판단에 주는 방향은 {quote(direction)}이다. "
                        f"근거 ID는 {quote(ref)}, 위치는 {quote(location)}이다.")
            expected.extend([text, direction, ref, location])
    rendered = " ".join(item)
    if [json.loads(value) for value in JSON_STRING.findall(rendered)] != expected:
        raise ValueError(f"Loss of L2 facts or citation fields for {row['item_id']}")
    return rendered


def prepare(case, labels):
    original, _, b, impact = original_inputs(case)
    rows = labels["items"]
    if len(rows) != len(original) or set(original) != {row["item_id"] for row in rows}:
        raise ValueError(f"{case}: format inputs must match all frozen original items")
    sources = labels.get("sources") or labels["source_index"]
    if isinstance(sources, list):
        sources = {source.get("source_id") or source["evidence_id"]: source for source in sources}
    raw_refs = set().union(*(evidence_ids(row[role]) for row in rows for role in ROLES))
    if raw_refs - sources.keys():
        raise ValueError(f"{case}: raw citations are outside the frozen source index {sorted(raw_refs - sources.keys())}")
    common = {
        "original_items": [{"item_id": row["item_id"], "question_type": row["question_type"],
                            "question": row["question"]} for row in rows],
        "b_facts": {f"B-{name}": fact for name, fact in b["facts"].items()},
        "b_rules": b["rules"], "original_price_impacts": impact,
        "materiality": "공개 근거가 선택을 바꿀 가능성 또는 적격 대안 5% 이상. 민감도 단독은 불충분.",
        "mandatory": b["mandatory"], "additional_k": 1,
    }
    structured = [{"item_id": row["item_id"], **{role: role_record(row[role], sources) for role in ROLES}} for row in rows]
    reduced = [{"item_id": row["item_id"], **{role: row[role]["judgment"] for role in ROLES}} for row in structured]
    prepared = {"L1": reduced, "L2": [prose(row) for row in structured], "L3": structured}
    exposed_refs = {fact["source_id"] for row in structured for role in ROLES for fact in row[role]["evidence"]}
    if exposed_refs != raw_refs:
        raise ValueError(f"{case}: at least one original citation was omitted from both renderings")
    rule = rule_table(rows, sources, impact, common["mandatory"])
    rule["fixed_k"] = common["mandatory"] + [row["item_id"] for row in rule["items"][:1]]
    return {"common": common, "reviews": prepared, "rule": rule,
            "common_refs": set(common["b_facts"]), "role_refs": raw_refs}


def run_format(case, condition, frozen, assessor=ask_proxy):
    base = frozen["common"]
    payload = {**base, "reviews": frozen["reviews"][condition]}
    if restricted_fields(payload):
        raise ValueError("Lookup or reference grades entered the model payload")
    cite = frozen["common_refs"] | (frozen["role_refs"] if condition != "L1" else set())
    expected = {row["item_id"] for row in base["original_items"]}

    def verify(result):
        ids = [row["item_id"] for row in result["items"]]
        if len(ids) != len(expected) or set(ids) != expected:
            raise ValueError("같은 원본 항목 ID를 각각 한 번 제출한다")
        for row in result["items"]:
            if set(row["evidence_ids"]) - cite:
                raise ValueError(f"{row['item_id']}는 현재 제시된 근거 ID만 사용해야 한다")
            if not row["reason"].strip():
                raise ValueError(f"{row['item_id']}에 판단 이유를 적는다")
            if row["action"] != "기록 보관" and not row["question_or_request"].strip():
                raise ValueError(f"{row['item_id']}에 고객 확인 질문 또는 자료 요청을 적는다")

    run = assessor(case, f"FORMAT_{condition}", INSTRUCTIONS, payload, DECISION, 3800, verify)
    mandatory = base["mandatory"]
    items = sorted(run["answer"]["items"], key=lambda row: (-row["priority"], row["item_id"]))
    nonmandatory = [{**row, "tie_key": str(row["priority"]), "eligible": row["action"] == "사람 검토"}
                    for row in items if row["item_id"] not in mandatory]
    eligible = [row["item_id"] for row in nonmandatory if row["eligible"]]
    return {"case": case, "condition": condition, "all_items": items, "items": nonmandatory,
            "fixed_k": mandatory + [row["item_id"] for row in nonmandatory[:1]],
            "operational": mandatory + eligible[:1], "waiting": eligible[1:],
            "mandatory": mandatory, "presented_refs": sorted(cite), "input_sha256": digest(payload),
            "reviewer": run["summary"], "evidence_dir": run["evidence_dir"]}


def run(only, workers, prepare_only, official=False):
    bundles = ("official/dev_labels.json", "validation_roles/official/labels.json") if official else (
        "proxy/labels_dev_mixed.json", "validation_roles/proxy/labels.json")
    labels = {k: v for path in bundles for k, v in bundle(OUT / path).items()}
    output = OUT / "official/formats" if official else OUTPUT
    selected = {case: labels[case] for case in (only or labels)}
    prepared = {case: prepare(case, values) for case, values in selected.items()}
    manifest = {"additional_lookup": False, "reviewer": "gpt-6.1-terra / Responses API" if official else "gpt-6.2-astra / Codex CLI",
                "effort": "medium", "prompt_sha256": digest(INSTRUCTIONS), "additional_k": 1,
                "input_contract": {case: {"common_sha256": digest(obj["common"]),
                                           "role_citation_ids": sorted(obj["role_refs"]),
                                           "condition_sha256": {key: digest(value) for key, value in obj["reviews"].items()},
                                           "source_location_and_fact_roundtrip": "pass"}
                                   for case, obj in prepared.items()}}
    frozen_path = output / ("freeze.json" if not only else "freeze_selected.json")
    if frozen_path.exists() and load(frozen_path) != manifest:
        raise ValueError("Frozen input or prompt changed; preserve the original format contract")
    dump(frozen_path, manifest)
    if prepare_only:
        return {"prepared_cases": len(prepared), "live_executions": 0}
    futures = {}
    failures = []
    rankings = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for case, obj in prepared.items():
            rankings[case] = {"case": case, "mandatory": obj["common"]["mandatory"], "L3-rule": obj["rule"]}
            for condition in CONDITIONS:
                futures[pool.submit(run_format, case, condition, obj, ask if official else ask_proxy)] = (case, condition)
        for future in as_completed(futures):
            case, condition = futures[future]
            try:
                result = future.result()
            except (RuntimeError, ValueError, TimeoutExpired, ValidationError) as exc:
                failures.append({"case": case, "condition": condition, "error_type": type(exc).__name__, "error": str(exc)})
                continue
            dump(output / case / (condition + ".json"), result)
            rankings[case][condition] = result
    summary = {"cases": rankings, "failures": failures, "model_calls_submitted": dict(Counter(
        condition for case in rankings.values() for condition in CONDITIONS if condition in case)),
        "assessment_scope": "grade-free rankings frozen before independent secondary scoring",
        "H2": {"status": "NOT_STARTED", "reason": "verified TRIZ signals and a separately frozen hold threshold required"}}
    dump(output / ("rankings.json" if not only else "rankings_selected.json"), summary)
    return {"cases": len(rankings), "submitted": sum(summary["model_calls_submitted"].values()), "failures": failures}


def audit(official=False):
    output = OUT / "official/formats" if official else OUTPUT
    manifest = load(output / "freeze.json")
    completed = load(output / "rankings.json")
    report = {"case_count": len(completed["cases"]), "cohorts": {"development": ["HDMS", "MELCON"],
              "validation": sorted(set(completed["cases"]) - {"HDMS", "MELCON"})}, "cases": {}, "H2": completed["H2"]}
    for case, rows in completed["cases"].items():
        inputs = {}
        usage_totals = Counter()
        model_seconds = 0.0
        top = {"L3-rule": rows["L3-rule"]["fixed_k"][len(rows["mandatory"]):]}
        for name in CONDITIONS:
            if name not in rows:
                continue
            ranking = rows[name]
            path = ROOT / ranking["evidence_dir"]
            if official:
                requests = sorted(path.glob("*_request.json"))
                attempts = [load(request) for request in requests]
                req = {**attempts[0], "input": json.loads(attempts[0]["input"])}
                if any(a["model"] != "gpt-6.1-terra" or a.get("tools") or a["reasoning"] != {"effort": "medium"}
                       for a in attempts):
                    raise ValueError(f"{case}/{name}: official request model, effort or tools mismatch")
            else:
                req = load(path / "request.json")
                attempts = load(path / "attempts.json")
                if any(row["tool_events"] for row in attempts) or req["model"] != "gpt-6.2-astra":
                    raise ValueError(f"{case}/{name}: isolation or model mismatch")
            if digest(req["instructions"]) != manifest["prompt_sha256"] or digest(req["input"]) != ranking["input_sha256"]:
                raise ValueError(f"{case}/{name}: submitted prompt/input hash differs from freeze")
            payload = req["input"]
            if restricted_fields(payload):
                raise ValueError(f"{case}/{name}: extra lookup or a reference-grade field was provided")
            if digest(payload["reviews"]) != manifest["input_contract"][case]["condition_sha256"][name]:
                raise ValueError(f"{case}/{name}: format input changed after freezing")
            inputs[name] = payload
            expected_order = sorted(ranking["all_items"], key=lambda row: (-row["priority"], row["item_id"]))
            if ranking["all_items"] != expected_order or ranking["fixed_k"] != (
                    rows["mandatory"] + [row["item_id"] for row in ranking["items"][:1]]):
                raise ValueError(f"{case}/{name}: changed ranking order or unmatched K")
            usage_totals["attempts"] += len(attempts)
            usage = [ranking["reviewer"]] if official else ranking["reviewer"]["turn_usage"]
            for record in usage:
                usage_totals.update({k: n for k, n in record.items() if type(n) is int})
            model_seconds += ranking["reviewer"]["elapsed_seconds"]
            top[name] = ranking["fixed_k"][len(rows["mandatory"]):]
        for name, input_packet in inputs.items():
            common = {k: v for k, v in input_packet.items() if k != "reviews"}
            if digest(common) != manifest["input_contract"][case]["common_sha256"]:
                raise ValueError(f"{case}/{name}: common information differs by input format")
        if "L1" in inputs and any(set(row) != {"item_id", "a0", "c"} for row in inputs["L1"]["reviews"]):
            raise ValueError(f"{case}: L1 contains role facts or citation fields")
        if "L2" in inputs and "L3" in inputs and inputs["L2"]["reviews"] != [prose(row) for row in inputs["L3"]["reviews"]]:
            raise ValueError(f"{case}: L2/L3 contain different facts or source references")
        report["cases"][case] = {"completed_conditions": sorted(inputs), "top_k1_extra": top,
                                  "usage": dict(usage_totals), "sum_session_seconds": round(model_seconds, 2)}
    dump(output / "audit.json", report)
    return {"case_count": report["case_count"], "checked_attempts": sum(row["usage"].get("attempts", 0)
                                                                          for row in report["cases"].values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append")
    parser.add_argument("--workers", type=int, choices=range(1, 7), default=4)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--official", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.official) if args.audit_only else run(args.case, args.workers, args.prepare_only,
                                                                     args.official), ensure_ascii=False))
