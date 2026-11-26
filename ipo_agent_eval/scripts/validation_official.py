"""Official configured Terra validation roles and prospective scoped perturbations."""

import argparse
import hashlib
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import product

import fitz
from bs4 import BeautifulSoup
from jsonschema import ValidationError
from openai import OpenAIError

from scripts.current_live import ask
from scripts.validation_roles import (
    A0_PROMPT,
    CACHE,
    CANDIDATES,
    DEST,
    ROOT,
    STATES,
    S,
    annual,
    arr,
    compact,
    dump,
    load,
    merge_proxy_labels,
    obj,
    proxy_schema,
    verify_role_answer,
)

HERE = DEST / "official"
PROOF = obj({"source": S, "quote": S})
DESIGN = obj({"context": arr(PROOF), "pivotal": arr(PROOF), "retained": arr(PROOF)})
SCREEN = obj(
    {
        "eligible": {"type": "boolean"},
        "common_proposition": S,
        "a0_ground": S,
        "c_ground": S,
        "counterevidence": S,
        "resolution_or_limit": S,
        "neutral_question": S,
        "A0": DESIGN,
        "C": DESIGN,
    }
)
SCREEN_RULE = """독립 사전 적격성 심사자다. 양 역할이 실제로 수용한 주된 이유가 같은 구체적 사실·범위인지, 중요한 반대근거가 관련 원문으로 해소됐는지 판단한다. 명목상 수용·동종업종·일부 제품 일치만으로 더 넓은 비교적격을 추정하지 않는다. 두 독립 근거의 공통 부분으로 구체적이고 원래 판단에 실제 영향을 미치는 좁은 사실은 검사할 수 있다. 미해결된 중요한 반대근거나 서로 다른 핵심 이유이면 제외하며 사유를 기록한다. 각각의 역할에 분리된 출처를 사용한다. A0는 A- 출처, C는 C- 출처만 쓸 수 있다. 실제 검사가 가능한 경우 발행사나 판단 맥락을 context에, 핵심 사실을 입증하는 증거 전부를 pivotal에, 주변의 다른 관련사실·한계를 retained에 넣는다. 각 인용은 제공된 출처의 짧고 연속된 원문 부분이며 표 머리와 숫자만으로 발행사/후보/연도 귀속이 불명확하면 추가 문구를 포함한다. 같은 내용을 중복하지 않는다. 비적격이면 설계 배열은 비운다. 중심 근거를 전부 제거하면 맥락과 retained만으로 그 사실을 확인할 수 없어야 한다. C의 인용과 중립 질문에는 상호·기업코드·최종선정·조정 이력·답·실험조건이 들어가지 않는다. 중립 질문은 결과를 암시하지 말고 검토 대상인 범위만 제시한다. 중복 가설, 미래 가정 또는 가상 수치를 추가하지 않는다."""
TRIAL = obj(
    {
        "decision": {"type": "string", "enum": STATES},
        "support": {"type": "string", "enum": ["proven", "contradicted", "unknown"]},
        "reason": S,
        "remaining": S,
        "evidence_ids": arr(S),
    }
)
TRIAL_RULE = """독립 검토자다. 제공된 근거만으로 질문의 범위 안에서 성립 여부(입증 proven, 반증 contradicted, 확인불충분 unknown), 수용·문제 제기·미확인 중 판단 하나, 근거 및 남은 한계를 기록하라. 자료에 없는 사실을 외부 기억으로 채우지 않는다. 나타난 행 ID만 인용한다. 자료가 없다는 이유만으로 반증이라고 판단하지 않는다. 발행사·후보·기간·단위 귀속을 구분하고, 제한된 사실로 전체 가치평가를 단정하지 않는다."""


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze_rules():
    path = HERE / "rules.json"
    if path.exists():
        return load(path)
    result = {
        "created_utc": datetime.now(UTC).isoformat(),
        "cases": list(CANDIDATES),
        "packets_sha256": {
            f"{case}/{p}": sha(DEST / case / p)
            for case, p in product(
                CANDIDATES, ["a0_input.json", "c_packet.json", "c_private.json"]
            )
        },
        "rule": "For every original item, both roles must independently support the same core proposition within comparable scope. Inspect material contrary evidence, substantiate its resolution with actual, dated primary evidence; exclude unresolved counterevidence, generic same-sector coincidence, mismatched causal grounds, or facts pivotal to only one role. No exclusion based on proxy results or grading. A qualified case must support a semantic-preserving transformation and an actual directional evidence intervention with prespecified predictions for each role. Include all qualifying dual accepts, not just J2.",
        "screening": "Use a fresh official screening call with official roles, source excerpts and claim scope only. No grades, rankings, proxy labels, prior eligibility, test outcomes, or operator suggestions about individual items. Apply structural comparability/citation gates first. Final material and expectations freeze before any test answer.",
        "assessor_exposure": "The orchestrating assistant previously saw TRUEN references during the separate proxy H2 task. Every official role, eligibility screen and perturbation evaluation is stateless with only its own explicit, grade-free inputs. No reference grades reopened or supplied in this task.",
        "roles": "Per-role/case independent official Responses calls. A0 uses item-targeted initial-filing pages. Neutral C receives issuer and masked candidates including real supplementary candidates, no selection labels. Compared to rejected legacy VC request, same packet and base instruction, generic method fields and clarification added; no specific earnings adjustment named.",
        "expected": "Original: reproduce supported core fact. Format: same support and decision after reordering unchanged statements. Directional: withdraw support when the crucial evidence is removed and any remaining evidence is insufficient, or change to contradictory if the predeclared alternative actually contradicts it. Record state and decision separately. No financial conclusion inferred from partial product overlap.",
    }
    dump(path, result)
    return result


def role(case, which):
    pinned = freeze_rules()["packets_sha256"]
    path = DEST / case / ("a0_input.json" if which == "A0" else "c_packet.json")
    assert sha(path) == pinned[f"{case}/{path.name}"]
    packet = load(path)
    rule = (
        A0_PROMPT
        if which == "A0"
        else (ROOT / "prompts/blind_reviewer.md").read_text(encoding="utf8")
        + "\n방법별 범주에는 제안에서 선택한 내용을 기입한다. 해당 자료가 지지하지 않으면 UNKNOWN이다. EPS와 재무비율을 계산할 자료가 없으면 가격을 추정하지 않는다. 각 후보 판정에 그 후보의 근거 ID를 포함한다. 회사명과 후보의 포함·제외 이력 추정은 금지한다."
    )
    stage = "V0" if which == "A0" else "VC_NEUTRAL"
    res = ask(
        case,
        stage,
        rule,
        packet,
        proxy_schema(which),
        5100 if which == "A0" else 3500,
        lambda a: verify_role_answer(which, packet, a),
    )
    record = {
        "role": which,
        "case": case,
        "provider": "OpenAI Responses API",
        "model": load(ROOT / "config/A0.json")["model"],
        "raw_response_id": res["raw_response_id"],
        "thread_id": res["raw_response_id"],
        "answer": res["answer"],
        "tool_item_types": [],
        "packet_sha256": sha(path),
        "method": "Independent initial assessment, stateless Responses request with no tools.",
        "evidence_dir": res["evidence_dir"],
        "summary": res["summary"],
    }
    assert record["raw_response_id"]
    dump(HERE / case / ("A0" if which == "A0" else "C_neutral") / "result.json", record)
    print(case, which, res["raw_response_id"], flush=True)


def roles():
    freeze_rules()
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {
            pool.submit(role, c, r): (c, r) for c, r in product(CANDIDATES, ["A0", "C"])
        }
        for future, pair in pending.items():
            try:
                future.result()
            except (
                OpenAIError,
                ValidationError,
                ValueError,
                RuntimeError,
                AssertionError,
                OSError,
            ) as err:
                errors.append(
                    {"role": pair, "type": type(err).__name__, "reason": str(err)[:500]}
                )
    if errors:
        dump(HERE / "run_errors.json", errors)
        raise RuntimeError(errors)


def base():
    merge_proxy_labels(official=True)
    bundle = load(HERE / "labels.json")
    cost = {}
    ids = set()
    for name, case in bundle["cases"].items():
        cost[name] = {}
        assert len(case["supplementary"]) == 1
        for role, path in case["run_paths"].items():
            record = load(ROOT / path)
            folder = ROOT / record["evidence_dir"]
            req = load(next(folder.glob("01_*_request.json")))
            packet = load(
                DEST / name / ("a0_input.json" if role == "A0" else "c_packet.json")
            )
            assert json.loads(req["input"]) == packet and req["text"]["format"][
                "schema"
            ] == proxy_schema(role)
            assert (
                not req.get("tools")
                and not req.get("previous_response_id")
                and req["store"] is False
            )
            assert (
                req["model"] == record["model"] and record["raw_response_id"] not in ids
            )
            ids.add(record["raw_response_id"])
            verify_role_answer(role, packet, record["answer"])
            s = record["summary"]
            cost[name][role] = {
                k: s[k]
                for k in [
                    "model_calls",
                    "format_repairs",
                    "input_tokens",
                    "output_tokens",
                    "elapsed_seconds",
                    "known_usage_cost_usd_standard_uncached",
                ]
            }
    assert len(ids) == 8 and bundle["n"] == 45
    dump(
        HERE / "role_audit.json",
        {
            "base_sha256": sha(HERE / "labels.json"),
            "cost": cost,
            "response_ids": sorted(ids),
            "case_comparability": {
                k: sum(r["c"]["comparable"] for r in l["items"])
                for k, l in bundle["cases"].items()
            },
            "three_reviews": [
                "원본의 모든 지정항목·물리 쪽·직접 인용을 다시 대조하고 각 회사당 진짜 보조 후보 하나를 확인했다.",
                "8개의 실전 API 요청 본문과 동결 자료·역할별 스키마·도구 미제공·이전 응답 미연결을 대조했다.",
                "45개 최종 행·참조 ID·후보별 독립 출처·역할별 비용을 대조하고 가격 자료 없는 제안은 제한했다.",
            ],
        },
    )


def screen_input(case, row, label):
    private = load(DEST / case / "c_private.json")
    raw = load(DEST / case / "a0_input.json")["original_physical_pages"]
    src = label["sources"]
    peer = next(
        (p for p in private["links"].values() if p["item_id"] == row["item_id"]), None
    )
    issuer = [
        k
        for k, v in private["sources"].items()
        if v["origin"] == "initial_filing_business_or_financials"
    ]
    pages = {src[e]["physical_page"] for e in row["a0"]["evidence_ids"]}
    pages.update(private["sources"][k]["physical_page"] for k in issuer)
    if peer:
        pages.update(
            int(p) for p, text in raw.items() if compact(peer["name"]) in compact(text)
        )
    elif row["c"].get("original_mapping_physical_page"):
        pages.add(row["c"]["original_mapping_physical_page"])
    sources = {}
    with fitz.open(CACHE / (private["receipt"] + ".pdf")) as doc:
        for p in sorted(pages):
            sources[f"A-p{p}"] = doc[p - 1].get_text(sort=True)
    common = list(dict.fromkeys(issuer + row["c"]["evidence_ids"]))
    for eid in common:
        sources["C-" + eid] = private["sources"][eid]["excerpt"]
    if peer:
        meta = annual(peer["ticker"])
        assert meta["published"] < private["receipt"][:8]
        section = next((s for s in meta["sections"] if s["key"] == "products"), None)
        if section:
            file = ROOT / section["snapshot"]
            assert sha(file) == section["sha256"]
            text = " ".join(
                BeautifulSoup(
                    file.read_bytes(), "html.parser", from_encoding="utf8"
                ).stripped_strings
            )
            sources["C-candidate-products-2022"] = text[:5200]
    return {
        "question": row["question"],
        "a0_ground": row["a0"],
        "c_ground": row["c"],
        "sources": sources,
    }


def banned(case):
    return [
        case,
        *[name for name, _ in CANDIDATES[case]],
        *[ticker for _, ticker in CANDIDATES[case]],
        "최종 선정",
        "비교기업 선정",
        "최종 비교",
        "공모가",
        "목표주가",
        "제외 여부",
        "편입 여부",
        "대조군",
        "통제군",
        "방향 변형",
        "TRIZ",
        {
            "GIGAVIS": "기가비스",
            "TRUEN": "트루엔",
            "PHILENERGY": "필에너지",
            "MANYO": "마녀공장",
        }[case],
    ]


def screen_one(case, row, label):
    packet = screen_input(case, row, label)

    def verify(a):
        if not a["eligible"]:
            return
        if not a["neutral_question"].strip():
            raise ValueError("State the neutral question")
        for role in ["A0", "C"]:
            if not a[role]["context"] or not a[role]["pivotal"]:
                raise ValueError("Each role needs actual context and pivotal evidence")
            for kind in ["context", "pivotal", "retained"]:
                for fact in a[role][kind]:
                    sid = fact["source"]
                    if (
                        not sid.startswith("A-" if role == "A0" else "C-")
                        or not fact["quote"].strip()
                        or compact(fact["quote"])
                        not in compact(packet["sources"].get(sid, ""))
                    ):
                        raise ValueError(
                            "Supply contiguous excerpts from the matching source " + sid
                        )
                    if role == "C" and any(
                        compact(term)
                        in compact(fact["quote"] + " " + a["neutral_question"])
                        for term in banned(case)
                    ):
                        raise ValueError(
                            "Remove names, selection clues and metadata from C quotes and question"
                        )

    res = ask(
        case,
        "OFFICIAL_ALIGNMENT_" + row["item_id"],
        SCREEN_RULE,
        packet,
        SCREEN,
        2700,
        verify,
    )
    dump(HERE / "screen" / (row["item_id"] + ".json"), res)
    return row["item_id"], res


def screen():
    bundle = load(HERE / "labels.json")["cases"]
    targets = [
        (c, r, l)
        for c, l in bundle.items()
        for r in l["items"]
        if r["a0"]["state"] == r["c"]["state"] == "수용" and r["c"]["comparable"]
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        done = list(pool.map(lambda p: screen_one(*p), targets))
    print(
        "screened",
        len(done),
        [i for i, r in done if r["answer"]["eligible"]],
        flush=True,
    )


def fingerprint(v):
    return hashlib.sha256(
        json.dumps(
            v, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def refine_design(key, answer):
    if key == "GIGAVIS-12":
        a, c = answer["A0"], answer["C"]
        # Candidate FC-BGA and flip-chip statements could independently re-prove the target.
        candidate, issuer = a["pivotal"]
        issuer_detail, candidate_detail = a["retained"]
        a["context"] = [issuer, issuer_detail]
        a["pivotal"] = [candidate, candidate_detail]
        a["retained"] = []
        c["context"].append(c["pivotal"].pop(0))
        prior = c["retained"][0]
        c["pivotal"].append(
            {**prior, "quote": "반도체 플립칩 외관검사장비가 31.7%였다."}
        )
        c["retained"] = [
            {**prior, "quote": "디스플레이와 이차전지 외관검사 장비도 판매했다."}
        ]
        answer["neutral_question"] = (
            "발행사와 후보의 검사장비 사업에 직접 겹치는 적용 대상이 확인되는가? 차이와 한계를 함께 검토하라."
        )
    if key == "GIGAVIS-01":
        fact = answer["A0"]["retained"][0]
        fact["quote"] = fact["quote"][fact["quote"].index("이는 현금의 유출이 없는") :]


def design():
    basefile = HERE / "labels.json"
    result = {
        "base_labels_sha256": sha(basefile),
        "rules_sha256": sha(HERE / "rules.json"),
        "eligibility": {},
        "tasks": [],
        "materials": {},
        "schema_hash": fingerprint(TRIAL),
        "instruction_hash": fingerprint(TRIAL_RULE),
        "pretrial_design_checks": "양 역할 모두 검토 대상 원래 질문에서 기간·귀속 등 정답 단서를 재노출하지 않는다. GIGAVIS-12의 잔존 FC-BGA·플립칩 검사 근거를 핵심 후보 근거로 이동해 방향 조건에서 모두 제거한다. 두 회사에서 실제 중첩이 있는지를 질문한다. GIGAVIS-01의 보상비용 잔존 문구에서 불필요한 연도 단서를 제거한다. 모든 인용 조각을 역할별 출처에 재대조한다.",
    }
    for case, label in load(basefile)["cases"].items():
        for row in label["items"]:
            key = row["item_id"]
            dual = (
                row["a0"]["state"] == row["c"]["state"] == "수용"
                and row["c"]["comparable"]
            )
            if not dual:
                result["eligibility"][key] = {
                    "eligible": False,
                    "reason": "역할 양측의 비교 가능한 수용 합의가 없음.",
                }
                continue
            p = HERE / "screen" / (key + ".json")
            screening = load(p)
            a = screening["answer"]
            result["eligibility"][key] = {
                k: v for k, v in a.items() if k not in ["A0", "C"]
            }
            result["eligibility"][key].update(
                screen_hash=sha(p), screen_run=screening["evidence_dir"]
            )
            if not a["eligible"]:
                continue
            refine_design(key, a)
            source_records = screen_input(case, row, label)["sources"]
            result["eligibility"][key]["neutral_question"] = a["neutral_question"]
            result["materials"][key] = {}
            for role in ["A0", "C"]:
                evidence = []
                pivots = set()
                for field in ["context", "pivotal", "retained"]:
                    for fact in a[role][field]:
                        fid = "F" + str(len(evidence) + 1)
                        assert compact(fact["quote"]) in compact(
                            source_records[fact["source"]]
                        )
                        source = fact["source"]
                        is_candidate = source == "C-candidate-products-2022" or (
                            source.startswith("C-E")
                            and label["sources"][source[2:]]["origin"]
                            == "candidate_own_2022_annual"
                        )
                        subject = (
                            ("후보 자료" if is_candidate else "발행사 자료")
                            if role == "C"
                            else "최초 신고서"
                        )
                        evidence.append(
                            {"id": fid, "subject": subject, "text": fact["quote"]}
                        )
                        if field == "pivotal":
                            pivots.add(fid)
                assert len(evidence) >= 2 and pivots and len(pivots) < len(evidence)
                question = a["neutral_question"]
                info = {"question": question}
                if role == "A0":
                    info["issuer"] = {
                        "GIGAVIS": "기가비스",
                        "TRUEN": "트루엔",
                        "PHILENERGY": "필에너지",
                        "MANYO": "마녀공장",
                    }[case]
                    if row["question_type"] == "J2":
                        info["candidate"] = row["question"].split("의 사업 비교")[0]
                parts = {
                    "original": evidence,
                    "format": list(reversed(evidence)),
                    "directional": [e for e in evidence if e["id"] not in pivots],
                }
                assert parts["original"] != parts["format"] and len(
                    parts["directional"]
                ) < len(evidence)
                if role == "C":
                    assert not any(
                        compact(t)
                        in compact(json.dumps([info, evidence], ensure_ascii=False))
                        for t in banned(case)
                    )
                for form, rows in parts.items():
                    payload = {**info, "evidence": rows}
                    task = {
                        "item": key,
                        "case": case,
                        "role": role,
                        "form": form,
                        "payload_hash": fingerprint(payload),
                        "pivots": sorted(pivots),
                        "expected_support": "unknown"
                        if form == "directional"
                        else "proven",
                        "expected_decision": "미확인"
                        if form == "directional"
                        else "수용",
                    }
                    result["tasks"].append(task)
                    result["materials"][key].setdefault(role, {})[form] = payload
    random.Random(261126).shuffle(result["tasks"])
    path = HERE / "triz/freeze.json"
    if path.is_file():
        existing = load(path)
        assert {k: v for k, v in existing.items() if k != "frozen_utc"} == result
        return existing
    result["frozen_utc"] = datetime.now(UTC).isoformat()
    dump(path, result)
    return result


def trial(task, spec):
    i, role, form = task["item"], task["role"], task["form"]
    packet = spec["materials"][i][role][form]
    assert fingerprint(packet) == task["payload_hash"]
    ids = {r["id"] for r in packet["evidence"]}

    def verify(a):
        if not a["evidence_ids"] or not set(a["evidence_ids"]) <= ids:
            raise ValueError("Cite one or more supplied evidence IDs only")

    saved = HERE / "triz/runs" / i / role / (form + ".json")
    if saved.exists():
        verify(load(saved)["answer"])
        return
    stage = f"T{i.split('-')[1]}{role}{form[0]}"
    res = ask(
        task["case"],
        stage,
        TRIAL_RULE,
        packet,
        TRIAL,
        1050,
        verify,
    )
    dump(saved, res)


def trials():
    spec = design()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda t: trial(t, spec), spec["tasks"]))
    print("completed", len(spec["tasks"]), "official perturbation calls", flush=True)


def started_utc(folder):
    events = [
        json.loads(s)
        for s in (folder / "events.jsonl").read_text(encoding="utf8").splitlines()
        if s.strip()
    ]
    return next(e["started_at_utc"] for e in events if e["event"] == "run_created")


def finalize():
    spec = design()
    bundle = load(HERE / "labels.json")
    assert sha(HERE / "labels.json") == spec["base_labels_sha256"]
    for case in bundle["cases"].values():
        case["triz"] = []
    records = {}
    ids = set()
    accounting = []
    for case, label in bundle["cases"].items():
        for p in label["run_paths"].values():
            accounting.append(("base", load(ROOT / p)))
    for i, elig in spec["eligibility"].items():
        if "screen_run" in elig:
            accounting.append(("screen", load(HERE / "screen" / (i + ".json"))))
    for task in spec["tasks"]:
        key, role, form = task["item"], task["role"], task["form"]
        res = load(HERE / "triz/runs" / key / role / (form + ".json"))
        assert res["raw_response_id"] not in ids
        folder = ROOT / res["evidence_dir"]
        raw_request = load(next(folder.glob("01_*_request.json")))
        assert (
            raw_request["instructions"] == TRIAL_RULE
            and fingerprint(json.loads(raw_request["input"])) == task["payload_hash"]
        )
        assert (
            raw_request["text"]["format"]["schema"] == TRIAL
            and raw_request.get("tools", []) == []
        )
        assert datetime.fromisoformat(started_utc(folder)) > datetime.fromisoformat(
            spec["frozen_utc"]
        )
        ids.add(res["raw_response_id"])
        accounting.append(("triz", res))
        answer = res["answer"]
        expected = (
            answer["support"] == task["expected_support"]
            and answer["decision"] == task["expected_decision"]
        )
        if form != "directional":
            expected = expected and bool(
                set(task["pivots"]) & set(answer["evidence_ids"])
            )
        records.setdefault(key, {}).setdefault(role, {})[form] = {
            "answer": answer,
            "expected_match": expected,
            "response_id": res["raw_response_id"],
            "evidence_dir": res["evidence_dir"],
        }
    for key, pair in records.items():
        checks = {}
        independent_observations = {}
        for role, r in pair.items():
            orig, fmt, direc = [r[k] for k in ["original", "format", "directional"]]
            fields = ["decision", "support"]
            independent_observations[role] = {
                "original_met_expectation": orig["expected_match"],
                "format_met_expectation": fmt["expected_match"],
                "original_and_format_same_observed_state": all(
                    orig["answer"][k] == fmt["answer"][k] for k in fields
                ),
                "direction_met_expectation": direc["expected_match"],
                "original_and_direction_different_observed_state": any(
                    orig["answer"][k] != direc["answer"][k] for k in fields
                ),
            }
            checks[role] = {
                "original_reproduced": orig["expected_match"],
                "format_preserved": orig["expected_match"] and fmt["expected_match"],
                "direction_responsive": orig["expected_match"]
                and direc["expected_match"],
            }
        all_pass = all(v for r in checks.values() for v in r.values())
        pair["checks"] = checks
        pair["independent_observations"] = independent_observations
        signal = {
            "item_id": key,
            "scope": spec["eligibility"][key]["common_proposition"],
            "original_facing_assessment": "양 역할에서 최초 수용을 재현했고 표시 형식 변경·핵심 근거 제거에도 기대대로 구별했다."
            if all_pass
            else "역할별 원본 수용 재현 또는 근거 안정성·반응성 검증이 일부 충족되지 않아 이 수용 합의를 추가로 지지하기 어렵다.",
            "role_checks": checks,
            "price_effect_verified": False,
        }
        bundle["cases"][key.split("-")[0]]["triz"].append(signal)
    totals = {}
    unique = set()
    starts = {}
    stops = {}
    for stage, record in accounting:
        assert record["raw_response_id"] not in unique
        unique.add(record["raw_response_id"])
        s = record["summary"]
        folder = ROOT / record["evidence_dir"]
        raw_responses = [load(p) for p in folder.glob("*_response.json")]
        assert any(r["id"] == record["raw_response_id"] for r in raw_responses)
        assert (
            s["execution_status"] == "SUBMITTED"
            and s["actual_model_answer"]
            and s["model"] == load(ROOT / "config/A0.json")["model"]
        )
        started = datetime.fromisoformat(started_utc(folder)).timestamp()
        starts.setdefault(stage, []).append(started)
        stops.setdefault(stage, []).append(started + s["elapsed_seconds"])
        t = totals.setdefault(
            stage,
            {
                "independent_tasks": 0,
                "model_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "standard_uncached_estimated_usd": 0.0,
                "cumulative_seconds": 0.0,
            },
        )
        t["independent_tasks"] += 1
        for m in ["model_calls", "input_tokens", "output_tokens"]:
            t[m] += s[m]
        t["standard_uncached_estimated_usd"] += s[
            "known_usage_cost_usd_standard_uncached"
        ]
        t["cumulative_seconds"] += s["elapsed_seconds"]
    for stage, counts in totals.items():
        counts["observed_parallel_span_seconds"] = round(
            max(stops[stage]) - min(starts[stage]), 3
        )
        counts["cumulative_seconds"] = round(counts["cumulative_seconds"], 3)
        counts["standard_uncached_estimated_usd"] = round(
            counts["standard_uncached_estimated_usd"], 6
        )
    failed_attempts = []
    for file in (DEST.parent / "live").glob("*/OFFICIAL_TRIZ_*/*/*/summary.json"):
        summary = load(file)
        if summary["execution_status"] != "FAILED":
            continue
        events = [
            json.loads(s)
            for s in (file.parent / "events.jsonl")
            .read_text(encoding="utf8")
            .splitlines()
        ]
        calls = [e for e in events if e["event"] == "model_call_started"]
        reserved = next(
            (
                e["request_and_reserved_cost_ceiling_usd"]
                for e in events
                if e["event"] == "budget_reservation"
            ),
            0,
        )
        failed_attempts.append(
            {
                "stage": summary["condition"],
                "evidence_dir": file.parent.relative_to(ROOT).as_posix(),
                "elapsed_seconds": summary["elapsed_seconds"],
                "transmission_starts": len(calls),
                "known_provider_usage": not calls,
                "known_usd": None if calls else 0,
                "reserved_ceiling_usd": reserved if calls else 0,
                "reason": summary.get("reason"),
                "interpretation": "Windows path-length failure. Request-started events determine transport count. Local failure before a saved provider response yields unknown usage.",
            }
        )
    totals["triz"]["total_transmissions_including_uncaptured"] = totals["triz"][
        "model_calls"
    ] + sum(r["transmission_starts"] for r in failed_attempts)
    totals["triz"]["additional_uncaptured_reserved_ceiling_usd"] = round(
        sum(r["reserved_ceiling_usd"] for r in failed_attempts), 6
    )
    totals["triz"]["cumulative_seconds_including_failed_runs"] = round(
        totals["triz"]["cumulative_seconds"]
        + sum(r["elapsed_seconds"] for r in failed_attempts),
        3,
    )
    assert len(ids) == len(spec["tasks"])
    dump(HERE / "labels_triz.json", bundle)
    dump(
        HERE / "triz/audit.json",
        {
            "criteria_precommitted": str((HERE / "rules.json").relative_to(ROOT)),
            "material_precommitted": str((HERE / "triz/freeze.json").relative_to(ROOT)),
            "base_sha256": sha(HERE / "labels.json"),
            "variant_sha256": sha(HERE / "labels_triz.json"),
            "results": records,
            "accounting": totals,
            "failed_local_attempts": failed_attempts,
            "eligibility": spec["eligibility"],
            "three_reviews": [
                {
                    "round": 1,
                    "check": "45개 원본과 19개 후보의 역할별 자료, 원문 인용, 기간과 추가 후보 포함을 검증했다.",
                    "remedy": "가린 C는 구체적인 손익 유형 단서 없는 공통 계약을 사용했다.",
                },
                {
                    "round": 2,
                    "check": "두 역할이 수용한 모든 항목을 독립 심사하고 범위·반대 근거와 별도 역할 증거를 기록했다.",
                    "remedy": "판단 근거가 다른 수용과 근거 제거로 방향 변화를 검사할 수 없는 항목은 별도 기록했다.",
                },
                {
                    "round": 3,
                    "check": "사전 저장 문항·형식·기대 및 원본별 결과·요청 ID와 실제 사용량 재확인.",
                    "remedy": "역할별 검증 실패도 보고했고, 선별기에 변형 답안이나 가상 수치는 전송하지 않았다.",
                },
            ],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", choices=["roles", "base", "screen", "design", "trials", "final"]
    )
    args = parser.parse_args()
    os.environ["IPO_RESUME_AFTER_CREDIT"] = "1"
    {
        "roles": roles,
        "base": base,
        "screen": screen,
        "design": design,
        "trials": trials,
        "final": finalize,
    }[args.stage]()
