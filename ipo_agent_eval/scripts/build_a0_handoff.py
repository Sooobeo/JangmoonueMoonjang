"""Assemble observed development failures; do not implement an A1 treatment."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/a0_implementation"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    comparison = read(HERE / "D5_v032_comparison.json")
    assert comparison["complete"] and len(comparison["runs"]) == 12
    grades = {r["run_id"]: r for name in ("D5_original_case_grading.json", "D5_new_case_grading.json")
              for r in read(HERE / name)["runs"]}
    assert len(grades) == 12
    failures = []
    groups = {"registration": [], "declaration": [], "available_work": []}

    def add(row, kind, description, impact, candidate=None, classification="A0_OBSERVED"):
        identifier = f"D6-{len(failures) + 1:03d}"
        directory = row["directory"]
        record = {"failure_id": identifier, "case_id": row["case_id"], "condition": row["condition"],
            "run_id": row["run_id"], "classification": classification, "failure_type": kind,
            "observation": description, "score_impact": impact,
            "tool_counts": row["tool_counts"], "pages": row["pages"],
            "input_snapshot_ids": row["snapshot_ids"], "calculation_ids": row["calculation_ids"],
            "tool_errors": row["tool_errors"],
            "evidence": [directory + "/events.jsonl", directory + "/summary.json",
                directory + "/snapshots.json", directory + "/calculations.json",
                directory + "/source_packet.json"],
            "grading_reference": {"run_id": row["run_id"], "metrics": grades[row["run_id"]]["metrics"]},
            "A1_candidate_group": candidate}
        failures.append(record)
        if candidate:
            groups[candidate].append(identifier)

    for row in comparison["runs"]:
        summary = row["summary"]
        grade = grades[row["run_id"]]
        if summary["execution_status"] == "FAILED":
            reason = summary["failure_reason"]
            classification = ("PLATFORM_FAILURE" if reason.startswith("API_ERROR") else
                "OUTPUT_LIMIT_OBSERVED" if row["condition"] == "B" and reason.startswith("MODEL_INCOMPLETE")
                else "EXECUTION_FAILURE")
            add(row, reason, {"detail": "유효 최종 제출 없이 종료했다. 원시 응답/오류와 사용량은 실행 폴더에 보존했다.",
                "diagnostics": grade.get("failure_observations", []),
                "interpretation": ("서버/API 오류로 종료했다. 오류 요청의 불명 사용량은0으로 합산하지 않는다."
                    if reason.startswith("API_ERROR") else
                    "출력 상한에서 중단됐다는 관찰이 단순한 레코드 길이만을 원인으로 확정하는 것은 아니다.")},
                "프로토콜 §11.1: 미제출 필수 F/K/J=0. 내용 오류·잘못된 완료·불필요 보류는 미관찰.",
                classification=classification)
        if row["condition"] != "A0":
            continue
        if any("format_repair" in r["file"] and r["status"] == "incomplete" for r in row["model_responses"]):
            add(row, "FORMAT_REPAIR_OUTPUT_LIMIT",
                "공통 형식 수정 1회가 2500 출력토큰 상한에서 절단됐다. 긴 최종 JSON의 재작성 가능성과 예약 상한을 구별해야 한다.",
                "최종 미제출 필수항목0. 추가 무상/숨은 재시도를 하지 않았다.", classification="COMMON_REPAIR_LIMIT")
        finalizing = [t for t in row["state_transitions"] if t["to"] == "FINALIZING"]
        if finalizing and not row["calculation_ids"] and row["snapshot_ids"] == ["X_EMPTY"]:
            add(row, "NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION",
                {"detail": "검색·열람 이후에도 수치 등록과 계산 없이 초기 snapshot으로 최종화했다.",
                 "finalizing_reasons": [t.get("reason") for t in finalizing],
                 "calculate_calls": row["tool_counts"].get("calculate", 0)},
                {"calculations": grade["metrics"]["calculations"], "methodology": grade["metrics"]["methodology"],
                 "interpretation": "계산 호출의 거부를 뜻하지 않는다. 실제 수행하지 않은 계산을 완료로 채점하지 않는다."}, "registration")
        if any(e["error_code"] == "INVALID_REVIEW" and "missing_inputs" in (e["message"] or "") for e in row["tool_errors"]):
            add(row, "UNRESOLVED_DECLARATION_MISMATCH",
                "최종 missing_inputs가 snapshot에 선언한 UNRESOLVED 업무 의존성 집합과 달라 기계 검증에서 거절됐다.",
                "계약 위반의 관찰이며 자연어 판단의 정답 여부를 자동 판정한 것이 아니다. 실패 실행의 필수 미제출은 0점.", "declaration")
        if grade.get("flags", {}).get("unnecessary_hold") is True:
            assessments = []
            submitted = read(ROOT / row["directory"] / "review.json")
            for original in grade.get("request_assessments", []):
                assessment = dict(original)
                assessment["evidence"] = [ref if ref.startswith("runs/") else row["directory"] + "/" + ref
                    for ref in original.get("evidence", [])]
                for collection, identifier in (("requests", "request_id"), ("escalations", "escalation_id")):
                    for index, request in enumerate(submitted[collection]):
                        if request[identifier] == original["id"]:
                            assessment["review_pointer"] = row["directory"] + f"/review.json#/{collection}/{index}"
                assessments.append(assessment)
            add(row, "AVAILABLE_WORK_DEFERRED",
                {"detail": "채점에서 코퍼스 안의 가능한 작업을 남겨 blocking 요청으로 넘긴 항목이 관찰됐다.",
                 "request_assessments": assessments,
                 "content_observations": grade.get("content_observations", []),
                 "grading_reference_file": "reports/a0_implementation/D5_original_case_grading.json",
                 "scope": "개별 요청 판정을 전체 HUMAN_REVIEW의 부당성으로 확대하지 않는다."},
                grade["metrics"], "available_work")

    proposals = {
        "registration": {
            "title": "탐색 중 등록·계산 진행 확인",
            "signal": "누적 입력 예약이 줄어드는 동안 search/read만 반복되고 snapshot=X_EMPTY 또는 계산 결과가 0개인 상태.",
            "action": "PREPARE 전 실제 읽은 핵심 원입력을 작은 묶음으로 등록하고 EVALUATE/민감도로 이어갈지 모델이 다시 계획하게 한다. 추가 검색 일부를 대체한다.",
            "limits": "코드가 정답 수치·포함 여부를 주입하지 않는다. 예산 부족이면 미완료를 보존한다."
        },
        "declaration": {
            "title": "최종화 전 의존성 선언 확인",
            "signal": "등록한 UNRESOLVED SELECTION 집합과 최종 missing_inputs 연결이 불일치하는 실제 실패.",
            "action": "탐색 단계에서 필요한 의존성 선언을 확인하고 최종화 입력에 현재 snapshot의 선언 집합을 명시하는 방안을 설계한다. COMMIT 후 탐색을 재개하거나 사실을 자동 수정하지 않는다.",
            "limits": "공통 계약 설명 개선이 필요한 부분은 B/A0에 함께 적용할 공통 수정으로 분리한다. A1만 받는 확인 절차의 효과는 후속 실험에서 측정한다."
        },
        "available_work": {
            "title": "코퍼스 안의 남은 작업과 외부 요청 구분",
            "signal": "EXPLORING 중 확인 지점에서 요청원장 또는 중간 작업계획이 수치 등록·산술·허용 코퍼스 추가열람 같은 내부 작업을 외부 blocking 요청으로 넘기려는지 확인한다. 이미 읽은 사실과 아직 읽지 않은 자료를 구별한다.",
            "action": "EXPLORING에서 남은 내부 작업을 현재 예약 예산으로 수행할 수 있는지 재계획한다. 외부 독립 자료 요청·사람 판단과 분리하고 예산이 막으면 BUDGET_LIMIT을 명시한다. FINALIZING/COMMIT에 진입한 뒤에는 조회·계산을 재개하지 않는다.",
            "limits": "이번 최종 답안의 문제를 근거로 후속 A1의 탐색 중 확인 지점을 설계하는 후보다. 중간 계획/원장이 없으면 별도 확인 단계와 그 호출 비용이 필요하며 탐지 성공을 보장하지 않는다. HPSP와 같은 근거 있는 사업 판단 이관을 자동 취소하지 않는다. 모델의 요청 상태 변경은 기록하고 추후 채점한다."
        }
    }
    candidates = []
    for name, ids in groups.items():
        if not ids:
            continue
        candidates.append({"candidate_id": "A1-C" + str(len(candidates) + 1), **proposals[name],
            "observed_A0_failure_ids": ids, "priority": "HIGH" if name == "registration" else "MEDIUM",
            "additional_cost": {"measured": False, "actual_usd": None,
                "planning_assumption": "한 추가 요청당 입력16000·출력1000토큰 가정; 실제 요청 길이/캐시에 따라 달라짐",
                "estimated_standard_usd_per_added_call": 0.021, "cache_write_ceiling_usd_per_added_call": 0.025,
                "added_model_calls_planning_range": [0, 3], "added_tools_planning_range": [0, 3],
                "note": "기존 탐색을 대체하면 추가 호출0. 동일16회/40도구/160k입력/16k출력/600초/$0.30 내에서 설계; 효과·비용은 아직 측정하지 않았다."},
            "evaluation": "개발 실패와 별도 W11 회귀에서 탐지·미탐·오탐, 제출·계산 완료와 J 점수, 추가 호출·비용을 각각 측정한다."})
    for failure in failures:
        linked = [c for c in candidates if failure["failure_id"] in c["observed_A0_failure_ids"]]
        failure["A1_candidate_ids"] = [c["candidate_id"] for c in linked]
        failure["expected_recheck"] = [c["action"] for c in linked] or ["공통 실행/외부 장애 후속조치로 분리하며 A1 효과의 근거로 사용하지 않는다."]
        failure["additional_cost"] = [c["additional_cost"] for c in linked] or {"measured": False, "actual_usd": None, "reason": "A1 개입 미배정"}
    report = {"stage": "D6", "batch": "D5_v032", "A1_implemented": False,
        "failure_records": failures, "A1_candidates": candidates,
        "shared_followups": [
            {"issue": "B의 5000토큰 단일 추출 응답이 반복 절단됨", "scope": "공통 계약/고정 기준선 실행 가능성",
             "next_action": "실제 부분 출력의 레코드 길이·공백 반복 등을 먼저 분리 진단하고 작은 전송 계약과 고정 분할 추출의 비용·모델 호출 영향을 새 버전 계획으로 검토. 원문·근거를 잘라 맞추거나 기존 실패를 대체하지 않는다.",
             "A1_effect_claim": False},
            {"issue": "0.3.1 이력 재전송 HTTP400", "scope": "공통 구현 결함", "status": "0.3.2 wire adapter와 실제API probe로 수정 검증", "A1_effect_claim": False},
            {"issue": "긴 최종 JSON 전체를 형식 수정 출력2500토큰으로 다시 쓰다 절단", "scope": "공통 형식 수정 계약",
             "next_action": "새 버전에서 형식 변경만 표현하는 제한된 patch 계약 또는 전체 응답 크기 제한의 실행 가능성 검토. 사실·판단 수정 금지와 공유1회·공통예산 조건 유지", "A1_effect_claim": False},
            {"issue": "API 서버 오류/불명 사용량", "scope": "외부 실행 장애", "next_action": "모든 시도·비용 불확실성 보존. 이번 max_retries=0 유지", "A1_effect_claim": False}
        ],
        "limits": ["개발기업6곳·조건별1회이며 최종 평가 표본 결과가 아니다.",
            "추가 비용은 계획 가정이고 청구액·사람 검토 시간·A1 효과를 측정한 값이 아니다.",
            "필수 미제출0과 관찰하지 못한 의미적 오류null을 구별한다."]}
    (HERE / "D6_failure_handoff.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 관찰된 실패와 A1 설계 인계", "", "0.3.2-dev 개발 비교 12회를 근거로 작성했다. A1은 아직 구현·실행하지 않았다. 아래 기록은 한 실행의 여러 문제를 나눠 적은 것이므로 기록 수를 실패 실행 수로 세지 않는다.", "",
        "실행별 도구 call_id·실제 열람 쪽·snapshot·계산 ID·점수 영향·재검토·비용 연결은 [전체 인계 JSON](D6_failure_handoff.json)에 있다. [실행 비교](D5_v032_comparison.json) 및 [채점 집계](D5_comparison_summary.md)와 대조한다.", "",
        "| 기록 | 사례/조건 | 관찰 유형 | 실행 근거 | A1 후보 |", "|---|---|---|---|---|"]
    for f in failures:
        lines.append(f"| {f['failure_id']} | {f['case_id']} {f['condition']} | {f['failure_type']} | [events](../../runs/{f['run_id']}/events.jsonl) | {', '.join(f['A1_candidate_ids']) or '공통/실행 후속'} |")
    lines += ["", "## 우선 검토할 A1 후보", ""]
    for c in candidates:
        lines += [f"### {c['candidate_id']} · {c['title']}", "", "실제 관찰: " + ", ".join(c["observed_A0_failure_ids"]), "",
            "탐지 후보: " + c["signal"], "", "예상 재검토: " + c["action"], "", c["limits"], "",
            "추가 비용은 미측정이다. 기존 탐색을 대체하면 추가 호출은 0이며, 계획 범위는 모델·도구 각각 0~3회다. 한 추가 호출을 입력 16,000·출력 1,000토큰으로 가정하면 표준 비캐시 $0.021, 동일 입력의 캐시 쓰기 상한 가정은 $0.025다. 실제 이력 길이·캐시·실행에 따라 달라진다. 공통 총예산 안에서 배치하며, 불가능하면 실패를 남긴다.", ""]
    lines += ["## 공통 보완과 분리할 항목", "",
        "B의 단일 추출은 출력 상한에서 중단됐다. ALT와 MILLIE에서는 많은 공백/탭 반복도 관찰돼 단순히 필요한 레코드가 길다는 원인만으로 설명하지 않는다. 전송 계약·고정 분할 추출을 새 버전에서 검토할 수 있지만, 이는 공통 기준선 실행 가능성 문제이며 A1의 효과로 주장하지 않는다.", "",
        "긴 최종 JSON을 공통 형식 수정 2,500토큰으로 재작성하다 중단된 사례도 있다. 형식만 바꾸는 제한된 patch 계약 등은 별도 공통 설계 검토 대상이다. 이번 결과에는 숨은 재시도·사실 수정·상한 확대를 적용하지 않았다.", "",
        "0.3.1의 이력 전송 HTTP 400은 공통 구현 결함으로 0.3.2에서 수정·검증했다. 이후 서버 오류와 사용량 불명은 실행 장애로 남겼다. 이런 사건을 A1의 방법론 개선 효과로 계산하지 않는다.", "",
        "후속 W11에서는 탐지·미탐·오탐, 수치 등록·계산·제출 완료율, F/K/J, 추가 호출·비용을 각각 측정한다. 공통 보완은 B/A0 양쪽에 적용하고 A1만 추가로 받는 절차와 버전을 분리한다. 평가 후보 12개는 W12 동결 전 답변을 받지 않는다.", ""]
    (HERE / "D6_failure_handoff.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"failures": len(failures), "candidates": len(candidates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
