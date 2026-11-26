"""Compare the baseline and expanded B/J1 scopes in fresh Terra sessions."""

import json
from concurrent.futures import ThreadPoolExecutor

from scripts.current_b import OUT, ROOT, dump
from scripts.current_j1_search import CASES, PROMPT, REVIEW
from scripts.current_live import ask, digest, load

DEST = OUT / "official" / "j1_pair"


def inputs(case, labels):
    case_path = OUT / "j1_search" / case
    existing = load(case_path / "freeze.json")
    expanded = load(case_path / "input.json")
    if digest(expanded) != existing["input_sha256"]:
        raise ValueError(f"{case}: J1 sensitivity input differs from its original frozen content")
    original = {row["item_id"]: row for row in labels["items"] if row["question_type"].startswith("J1")}
    expected = [row["item_id"] for row in expanded["j1_items"]]
    if len(expected) != len(original) or set(expected) != set(original):
        raise ValueError(f"{case}: paid comparison does not cover every J1 item")
    roles = [{"item_id": key, "question": original[key]["question"],
              "a0": original[key]["a0"]["reason"], "c": original[key]["c"]["reason"]} for key in expected]
    if roles != expanded["j1_items"]:
        raise ValueError(f"{case}: prior J1 packet differs from the completed Terra roles")
    original_only = {**expanded, "new_original_pages": {}}
    if expanded["new_original_pages"]:
        original_only["B_LTM_sensitivity"] = {"status": "미산출", "reason": "기존 제공 원문에 재계산에 필요한 동일 범위의 회계 행이 모두 들어 있지 않음"}
    arms = {"baseline": original_only, "expanded": expanded}
    order = ["baseline", "expanded"] if case == "HDMS" else ["expanded", "baseline"]
    freeze = {"case": case, "official_roles": {role: labels[role]["summary"]["run_id"] for role in ("a0_run", "c_run")},
              "official_model": "gpt-6.1-terra", "prompt_sha256": digest(PROMPT), "J1_items": expected,
              "order": order, "input_hashes": {arm: digest(p) for arm, p in arms.items()},
              "common_baseline_excerpts": digest(expanded["baseline_excerpts"]),
              "added_pages": sorted(expanded["new_original_pages"]),
              "scope": "same-prompt post-hoc development comparison of the expanded accounting coverage and scenario, not a new H1 outcome"}
    path = DEST / case / "freeze.json"
    if path.exists() and load(path) != freeze:
        raise ValueError(f"{case}: frozen J1 comparison was changed")
    dump(path, freeze)
    return freeze, arms


def compare(case, prepared):
    frozen, arms = prepared
    rows = {}
    expected = set(frozen["J1_items"])
    for arm in frozen["order"]:
        payload = arms[arm]
        allowed = set(payload["baseline_excerpts"]) | set(payload["new_original_pages"])

        def verify(answer, allowed=allowed):
            ids = [row["item_id"] for row in answer["items"]]
            if len(ids) != len(expected) or set(ids) != expected:
                raise ValueError("각 입력 J1 항목을 한 번 제출한다")
            if any(not row["evidence_ids"] or not set(row["evidence_ids"]) <= allowed for row in answer["items"]):
                raise ValueError("실제로 제공된 근거 ID를 사용한다")

        out = ask(case, f"J1_OFFICIAL_{arm.upper()}", PROMPT, payload, REVIEW, 2200, verify)
        summary = out["summary"]
        if set(summary["returned_models"]) != {frozen["official_model"]}:
            raise ValueError(f"{case}/{arm}: actual return model mismatch")
        recorded = load(ROOT / out["evidence_dir"] / f"01_J1_OFFICIAL_{arm.upper()}_request.json")
        if recorded["instructions"] != PROMPT or digest(json.loads(recorded["input"])) != frozen["input_hashes"][arm]:
            raise ValueError(f"{case}/{arm}: recorded model request contains different input")
        rows[arm] = {"submitted": True, "session": out["evidence_dir"], "summary": summary,
                     "items": out["answer"]["items"], "new_pages": sorted(payload["new_original_pages"]),
                     "B_LTM_sensitivity": payload["B_LTM_sensitivity"]}
        dump(DEST / case / f"{arm}.json", rows[arm])
    result = {"case": case, "same_model_prompt_roster": True, "paired": rows}
    dump(DEST / case / "result.json", result)
    return result


if __name__ == "__main__":
    data = {row["case_id"]: row for row in load(OUT / "official" / "dev_labels.json")["cases"]}
    plans = {case: inputs(case, data[case]) for case in CASES}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda case: compare(case, plans[case]), CASES))
    dump(DEST / "summary.json", {"scope": "Terra official development J1 follow-up", "cases": results})
    print("Completed", len(results), "official J1 pairs")
