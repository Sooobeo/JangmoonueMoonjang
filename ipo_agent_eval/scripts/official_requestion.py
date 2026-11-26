"""Audit the actual one-slot A1 referrals for repeated, attributable two-role disputes."""

import hashlib
from datetime import UTC, datetime
from itertools import combinations

from ipo_eval.agent_loop import output_json
from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import load
from scripts.current_selector import evidence_ids, read_cases, state

HERE = OUT / "official/requestion"
RULES = OUT / "official/recovery_protocol.md"
FIRMS = ("HDMS", "MELCON", "GIGAVIS", "TRUEN", "MANYO", "PHILENERGY")
ASSESSMENT = {
    "H02": (
        "미확인",
        "문제 제기",
        "한쪽의 개별 결론 부재",
        "A0는 후보의 조선 중심 매출과 엔진·AM 연관성을 모두 언급하면서 개별 편입·배제는 판단하지 않았다. C는 신조선 매출 83.1%를 근거로 제외를 제안했다. 남은 질문은 엔진·AM 연관성이 주력 사업의 차이를 보완하는지다. A0의 출처가 밝힌 선정 사유를 A0 자신의 찬성 판단으로 해석할 수 없다.",
    ),
    "M03": (
        "문제 제기",
        "문제 제기",
        "두 역할의 같은 공정 차이 지적",
        "A0와 C 모두 고압 수소 어닐링과 포토공정 환경제어의 기능 차이를 확인했다. 심사자에게 넘어간 점은 온습도 관련 매출 기준 50% 충족 근거와 동일 배수 비교의 타당성이다. A0가 배제를 확정하지 않은 점은 C와 반대되는 포함 제안이 아니다.",
    ),
    "GIGAVIS-08": (
        "문제 제기",
        "미확인",
        "가림 범위의 손익조정 자료 부족",
        "A0는 우리사주 관련 주식보상비용 전액 가산의 대칭성과 세효과를 문제 삼았다. C는 해당 비용 성격·금액을 받지 못해 일반적 자료 요청에 그쳤다. 원문으로 가산액·경위를 확인한 뒤에도 비교기업 조정과 법인세 효과는 남지만 C가 그 가산에 찬성한 것은 아니다.",
    ),
    "TRUEN-10": (
        "문제 제기",
        "문제 제기",
        "두 역할의 같은 제품·매출원 차이 지적",
        "A0와 C 둘 다 IP 카메라와 AI 개발·데이터 분석 소프트웨어의 주된 제품·매출원 차이를 지적했다. 넓은 빅데이터·AI 선정 기준을 적용하고 배수를 유지한 근거가 검토 대상이다. 심사자의 질문은 양측 공통 문제제기에서 비롯됐다.",
    ),
    "MANYO-11": (
        "미확인",
        "문제 제기",
        "한쪽 정보 부족이 원문 대조로 해소",
        "A0는 화장품 기준 통과 사실을 확인했지만 매출 구성을 확인하지 못해 수용을 확정하지 않았다. C의 E6으로 생활용품 64% 및 직접 생산을 확인하면서 매출 구성에 대한 차이는 해소되었다. 남은 질문은 화장품 기준을 통과한 이 회사를 외부 OEM·ODM 중심 브랜드의 비교기업으로 유지할지다.",
    ),
    "PHILENERGY-10": (
        "문제 제기",
        "미확인",
        "공정 차이에 동의하고 이익 지속성은 한쪽 범위 밖",
        "A0와 C 모두 적층·조립 대 활성화·충방전 공정 차이를 언급했다. A0는 LTM 흑자와 1분기 이익의 집중도도 문제 삼았지만 C는 재무조건·배수를 받지 못했다. 사업·이익 지속성에 대한 판단을 서로 반대로 내린 사례가 아니다.",
    ),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def criteria():
    path = HERE / "criteria.json"
    if not path.exists():
        dump(
            path,
            {
                "frozen_utc": datetime.now(UTC).isoformat(),
                "protocol_sha256": sha(RULES),
                "sample": list(FIRMS),
                "list": "Final full-signal official A1 operating allocation, including mandatory plus selected human-review rows. Waiting, document requests, archive, fixed-K rank and L3 control do not establish actual human transfer.",
                "comparison": "Compare each role's source-grounded position on the specific subject, period and concrete decision; matching opposite conclusions with an unresolved question must occur in at least two distinct companies with the same substantive mechanism. Unknown without a contrary claim, unobservable prices, scope mismatches, joint concerns or a common J-family do not suffice.",
                "extra_round": "Only if a repeated live dispute is found. Freeze paired baseline rankings, role evidence, allowed original filing sections, one neutral clarification question and response contract before the one extra independent official round. Keep original H1 outcomes immutable.",
                "prior_exposure": "Audit operator previously saw the separate proxy H2 TRUEN reference. This audit reads only official role labels, final official A1 operation/raw evidence and protocol; no reference grades or effectiveness results.",
                "information_at_freeze": "Three official referrals (HDMS, MELCON, TRUEN) already inspected against the unchanged public recovery rule. Three remaining full-signal validation ranks were unavailable during that inspection.",
            },
        )
    return load(path)


def inspect_routed(case, label, arm):
    """Preserve role scope, exact question and source pointers for each real transfer."""
    by_label = {r["item_id"]: r for r in label["items"]}
    by_rank = {r["item_id"]: r for r in arm["ai"]["items"]}
    for key in arm["ai"]["operational"]:
        item = by_label[key]
        rank = by_rank.get(key)
        if rank is not None:
            assert rank["action"] == "사람 검토"
        a, c = item["a0"], item["c"]
        compared = (
            item.get("comparison_status") == "비교 가능"
            if "comparison_status" in item
            else bool(a["comparable"] and c["comparable"])
        )
        evidence = {}
        for role, obj in [("a0", a), ("c", c)]:
            ids = sorted(evidence_ids(obj))
            evidence[role] = {
                "state": state(obj),
                "reason": obj["reason"],
                "source_ids": ids,
                "evidence_provided": obj.get("evidence_provided"),
                "comparable": obj.get("comparable"),
                "scope": obj.get("scope") or item.get("comparison_scope_note"),
                "raw_proposal": obj.get("native_decision") or obj.get("native_choice"),
            }
        yield {
            "item_id": key,
            "question_type": item["question_type"],
            "registry_question": item["question"],
            "comparability_record": item.get("comparison_status"),
            "scope_note": item.get("comparison_scope_note"),
            "role_judgments": evidence,
            "roles_comparable": compared,
            "mandatory": key in arm["mandatory"],
            "selector_reasons": rank["reason"] if rank else "B 필수",
            "actual_transfer_question": rank["question_or_request"]
            if rank
            else "B 필수",
            "selector_source_ids": rank["evidence_ids"] if rank else [],
            "selector_priority": rank["priority"] if rank else None,
            "role_scope": label.get("c_scope", label.get("scope")),
        }


def extract():
    criteria()
    labels = {
        **read_cases(OUT / "official/dev_labels.json"),
        **read_cases(OUT / "validation_roles/official/labels_triz.json"),
    }
    assert set(labels) == set(FIRMS)
    results = {}
    for case in FIRMS:
        path = OUT / "ranking/terra" / (case + ".json")
        if not path.is_file():
            continue
        rank = load(path)
        assert rank["selector_condition"] == "TERRA" and rank["case"] == case
        assert rank["triz"] == labels[case].get("triz", [])
        rows = rank["ai"]["items"]
        grouped = {
            "actual_human_referrals": rank["ai"]["operational"],
            "waiting_for_human_review": rank["ai"]["waiting"],
            "document_requests": [
                r["item_id"] for r in rows if r["action"] == "자료 요청"
            ],
            "archived": [r["item_id"] for r in rows if r["action"] == "기록 보관"],
        }
        whole = [k for vals in grouped.values() for k in vals]
        assert len(whole) == len(set(whole)) == len(labels[case]["items"])
        results[case] = {
            "source": path.relative_to(ROOT).as_posix(),
            "sha256": sha(path),
            "selector_run": rank["decision_run"],
            "role_bundle": relative_bundle(case),
            "action_partition": grouped,
            "routed_details": list(inspect_routed(case, labels[case], rank)),
        }
    return results


def relative_bundle(case):
    p = OUT / (
        "official/dev_labels.json"
        if case in ("HDMS", "MELCON")
        else "validation_roles/official/labels_triz.json"
    )
    return {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)}


def audit():
    firms = extract()
    assert set(firms) == set(FIRMS)
    routed = {}
    action_counts = {}
    for f in firms.values():
        folder = ROOT / f["selector_run"]
        rawpath = max(folder.glob("*_response.json"))
        raw = load(rawpath)
        selected = {r["item_id"]: r for r in output_json(raw)["items"]}
        f["raw_selector_response_id"] = raw["id"]
        f["raw_selector_response_sha256"] = sha(rawpath)
        for kind, items in f["action_partition"].items():
            action_counts[kind] = action_counts.get(kind, 0) + len(items)
        for row in f["routed_details"]:
            key = row["item_id"]
            a, c, reason, scope = ASSESSMENT[key]
            assert [row["role_judgments"][r]["state"] for r in ["a0", "c"]] == [a, c]
            submission = selected[key]
            assert submission["action"] == "사람 검토"
            assert (
                submission["question_or_request"] == row["actual_transfer_question"]
                and submission["reason"] == row["selector_reasons"]
            )
            row.update(
                opposed_source_grounded_claims=False,
                dispute_qualification=reason,
                substantive_check=scope,
            )
            routed[key] = row
    assert set(routed) == set(ASSESSMENT)
    pairs = [
        {
            "first": a,
            "second": b,
            "both_have_source_grounded_opposition": routed[a][
                "opposed_source_grounded_claims"
            ]
            and routed[b]["opposed_source_grounded_claims"],
        }
        for a, b in combinations(routed, 2)
    ]
    assert len(pairs) == 15 and not any(
        p["both_have_source_grounded_opposition"] for p in pairs
    )
    report = {
        "audited_utc": datetime.now(UTC).isoformat(),
        "criteria": str((HERE / "criteria.json").relative_to(ROOT)),
        "protocol_sha256": sha(RULES),
        "condition": "Final full-signal official gpt-6.1-terra A1 operating allocations",
        "companies": firms,
        "actual_action_totals": action_counts,
        "all_cross_firm_pairs": pairs,
        "similar_groups_examined": [
            {
                "items": ["H02", "MANYO-11"],
                "finding": "둘 다 후보 매출 구성이 발행사와 다르고 C는 배제를 제안했다. H02의 A0는 개별 판단을 내리지 않았고, MANYO-11의 매출 구성 미확인은 E6로 해소됐다. 같은 양측의 상반된 사실 주장은 없다.",
            },
            {
                "items": ["M03", "TRUEN-10", "PHILENERGY-10"],
                "finding": "제품·공정이 다르다는 점을 두 역할이 공통으로 관찰했다. 반도체 온습도 매출 기준, 카메라·소프트웨어 제품 차이, 2차전지 공정과 이익 지속성은 각각 다른 후속 질문이다.",
            },
            {
                "items": ["GIGAVIS-08", "PHILENERGY-10"],
                "finding": "이익 판단도 등장하지만 주식보상 조정 대칭성과 LTM 이익 지속성의 쟁점은 다르다. 어느 쪽도 C가 해당 재무 자료로 반대 결론을 제시하지 않았다.",
            },
        ],
        "eligible_repeated_groups": [],
        "condition_met": False,
        "additional_model_calls": 0,
        "original_rankings_modified": False,
        "reference_grades_opened_for_this_audit": False,
        "conclusion": "6개 실제 이관 모두 미해결된 확인 질문이 있지만, 같은 구체적 쟁점에서 서로 비교 가능한 A0/C가 근거를 들어 반대 결론을 내린 두 기업은 없었다. 재질문 조건 미충족.",
        "three_reviews": [
            "공식 전수 순위와 역할 입력의 신호를 대조하고 모든 항목을 실제 이관·사람 대기·자료 요청·기록 보관으로 1회씩 분류했다.",
            "실제 이관된 6개 질문과 이유를 보관된 API 원응답에서 대조하고, 두 역할의 근거와 가림 범위, 추가 원문으로 해소된 사실을 따로 기록했다.",
            "15개 기업 쌍과 주제가 비슷한 3개 묶음을 대조했다. 공통 이견이 없는 이관, 한쪽 미확인, 자료 요청과 미선정 대기는 실험 트리거에서 제외했다.",
        ],
    }
    dump(HERE / "trigger.json", report)
    return report


if __name__ == "__main__":
    report = audit()
    print(report["actual_action_totals"], report["condition_met"])
