"""Run the frozen, one-case proxy hold experiment and unlock references after ranking."""

import argparse
import hashlib
from datetime import UTC, datetime
from itertools import product

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import load
from scripts.current_selector import grade_free_case, read_cases
from scripts.current_validation import cases, prepare, verify

HERE = OUT / "deferral"
CASE = "TRUEN"
FULL = OUT / "ranking/proxy/TRUEN.json"
PLAIN = OUT / "ranking/proxy_without_triz/TRUEN.json"
REDUCED = HERE / "remaining_selector.json"
LABELS = OUT / "validation_roles/proxy/labels_triz.json"
TRIZ = OUT / "validation_roles/proxy/triz/audit.json"
REFERENCE = OUT / "validation/codex/TRUEN.json"
COMMIT = HERE / "ranking_commit.json"
USAGE = [
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
]


def utc():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def fixed_inputs():
    frozen = load(HERE / "freeze.json")
    for name, h in frozen["preoutcome_input_sha256"].items():
        assert sha(OUT / name) == h, name
    hold = frozen["hold_candidates_ordered"]
    audit = load(TRIZ)
    for item, role in product(hold, ["A0", "C"]):
        checks = audit["tests"][item][role]["checks"]
        assert set(checks) == {
            "original_reproduced",
            "format_preserved",
            "direction_responsive",
        } and all(checks.values())
    assert audit["actual_sessions"] == 12
    b = load(OUT / "validation/b.json")[CASE]
    assert set(hold).isdisjoint(b["mandatory"])
    return hold


def selector_run():
    hold = fixed_inputs()
    assert FULL.is_file() and PLAIN.is_file()
    return grade_free_case(CASE, read_cases(LABELS)[CASE], proxy=True, held_items=hold)


def compare_selector_requests(runs, held):
    """Check the sent contract and common context before opening the reference."""
    proof = {}
    for stage in ["lookup_run", "decision_run"]:
        requests = {
            arm: load(ROOT / load(file)[stage] / "request.json")
            for arm, file in runs.items()
        }
        full = requests["full_with_signal"]
        for req in requests.values():
            for key in ["model", "schema", "instructions"]:
                assert req[key] == full[key], (stage, key)
        for arm, req in requests.items():
            a, b = req["input"], full["input"]
            for k in [
                "original_sources",
                "b_record",
                "original_price_impacts",
                "materiality",
                "mandatory",
                "additional_k",
            ]:
                assert a[k] == b[k], (stage, arm, k)
            assert a["additional_k"] == 1
            if stage == "lookup_run":
                assert a["available_pages"] == b["available_pages"]
            cut = held if arm == "hold_with_signal" else []
            assert a["original_items"] == [
                row for row in b["original_items"] if row["item_id"] not in cut
            ]
            assert a["physical_page_index"] == {
                k: v for k, v in b["physical_page_index"].items() if k not in cut
            }
            assert a["triz"] == ([] if arm == "full_without_signal" else b["triz"])
        proof[stage] = {
            "matched_model": full["model"],
            "same_schema_and_instructions": True,
            "same_original_source_count": len(full["input"]["original_sources"]),
            "shared_page_catalog": stage == "lookup_run",
            "all_request_sha256": {
                a: sha(ROOT / load(p)[stage] / "request.json") for a, p in runs.items()
            },
        }
    return proof


def commit():
    if COMMIT.is_file():
        existing = load(COMMIT)
        for path, h in existing["source_sha256"].items():
            assert sha(ROOT / path) == h, path
        return existing
    held = fixed_inputs()
    labels = read_cases(LABELS)[CASE]
    keys = {row["item_id"] for row in labels["items"]}
    full_runs = {
        "full_without_signal": PLAIN,
        "full_with_signal": FULL,
        "hold_with_signal": REDUCED,
    }
    result = {
        "case": CASE,
        "frozen_utc": utc(),
        "freeze_sha256": sha(HERE / "freeze.json"),
        "source_sha256": {relative(path): sha(path) for path in full_runs.values()},
        "reference_visible_to_compiler": False,
        "arms": {},
        "sent_request_comparison": compare_selector_requests(full_runs, held),
    }
    full = load(FULL)
    mandatory = full["mandatory"]
    l3 = [r for r in full["rule"]["items"] if r["item_id"] in held]
    assert [r["item_id"] for r in l3] == held
    assert set(mandatory).isdisjoint(held)
    original_signals = labels["triz"]
    for arm, filename in full_runs.items():
        run = load(filename)
        assert run["case"] == CASE and run["selector_condition"] == "CODEX_PROXY"
        assert run["mandatory"] == mandatory
        reduced = filename == REDUCED
        assert run["triz"] == ([] if filename == PLAIN else original_signals)
        rows = run["ai"]["items"]
        ranked = [row["item_id"] for row in rows]
        tie = {row["item_id"]: "AI-" + row["tie_key"] for row in rows}
        if reduced:
            assert run["held_items"] == held and set(held).isdisjoint(ranked)
            ranked += held
            tie.update({r["item_id"]: "L3-" + r["tie_key"] for r in l3})
        assert (
            len(ranked) + len(mandatory) == len(keys)
            and set(ranked) | set(mandatory) == keys
        )
        assert run["ai"]["fixed_k"] == mandatory + ranked[:1]
        assert set(run["ai"]["operational"]) <= set(ranked) | set(mandatory)
        result["arms"][arm] = {
            "source": relative(filename),
            "rank_nonmandatory": ranked,
            "tie": tie,
            "mandatory": mandatory,
            "fixed_k": run["ai"]["fixed_k"],
            "operational": run["ai"]["operational"],
            "waiting": run["ai"]["waiting"],
            "selector_row_count": run["common_item_count"],
            "deferred_tail": held if reduced else [],
        }
    dump(COMMIT, result)
    return result


def run_usage(path):
    run = load(path)
    stages = []
    for key in ["lookup_run", "decision_run"]:
        folder = ROOT / run[key]
        result = load(folder / "result.json")
        attempts = load(folder / "attempts.json")
        assert all(a["returncode"] == 0 and not a["tool_events"] for a in attempts)
        usage = [u for attempt in attempts for u in attempt["turn_usage"]]
        invalid_extra_ids = []
        if key == "decision_run" and (folder / "invalid.json").is_file():
            rejected = {r["item_id"] for r in load(folder / "invalid.json")["items"]}
            expected = {
                r["item_id"]
                for r in load(folder / "request.json")["input"]["original_items"]
            }
            invalid_extra_ids = sorted(rejected - expected)
            assert {r["item_id"] for r in result["answer"]["items"]} == expected
        stages.append(
            {
                "source": relative(folder),
                "model": result["summary"]["model"],
                "calls": len(attempts),
                "rejected_extra_item_ids": invalid_extra_ids,
                "elapsed_seconds": result["summary"]["elapsed_seconds"],
                "tokens": {k: sum(u.get(k, 0) for u in usage) for k in USAGE},
            }
        )
    calls = sum(s["calls"] for s in stages)
    elapsed = round(sum(s["elapsed_seconds"] for s in stages), 3)
    outputs = sum(s["tokens"]["output_tokens"] for s in stages)
    return {
        "calls": calls,
        "observed_budget_checks": {
            "selector_elapsed_at_most_180_seconds": elapsed <= 180,
            "two_stages_plus_at_most_one_total_repair": calls <= 3,
            "at_most_four_lookup_pages": len(run["lookup_pages"]) <= 4,
            "output_tokens_at_most_12000": outputs <= 12000,
            "usd_limit_measurable": False,
        },
        "tokens": {k: sum(s["tokens"][k] for s in stages) for k in USAGE},
        "selector_elapsed_seconds": round(sum(s["elapsed_seconds"] for s in stages), 3),
        "selected_pages": run["lookup_pages"],
        "stages": stages,
    }


def outcome(chosen, major, pending):
    selected = set(chosen)
    missed = sorted(major - selected)
    uncertain = sorted(pending - selected)
    return {
        "selected": chosen,
        "confirmed_major_missed": missed,
        "confirmed_major_caught": sorted(major & selected),
        "miss_bounds_if_pending_regraded": [len(missed), len(missed) + len(uncertain)],
        "pending_outside_selection": uncertain,
        "observed_major_recall": len(major & selected) / len(major) if major else None,
    }


def measure(arm, major, other, pending):
    ranked = arm["rank_nonmandatory"]
    index = {key: n for n, key in enumerate(ranked)}
    pairs = list(product(major & set(ranked), other & set(ranked)))
    wins = ties = 0
    for positive, negative in pairs:
        if arm["tie"][positive] == arm["tie"][negative]:
            ties += 1
        elif index[positive] < index[negative]:
            wins += 1
    return {
        "pair_concordance": (wins + ties / 2) / len(pairs) if pairs else None,
        "positive_vs_other_pairs": len(pairs),
        "strict_wins": wins,
        "ties": ties,
        "common_k": {
            str(k): outcome(arm["mandatory"] + ranked[:k], major, pending)
            for k in [1, 2, 3]
        },
        "operational": outcome(arm["operational"], major, pending),
    }


def compare_costs(test, base):
    return {
        "calls": test["calls"] - base["calls"],
        "wall_seconds": round(test["wall_seconds"] - base["wall_seconds"], 3),
        "cumulative_session_seconds": round(
            test["cumulative_session_seconds"] - base["cumulative_session_seconds"], 3
        ),
        "tokens": {k: test["tokens"][k] - base["tokens"][k] for k in USAGE},
        "incremental_usd": None,
    }


def costs():
    triz = load(TRIZ)
    runs = {
        name: run_usage(p)
        for name, p in [
            ("full_without_signal", PLAIN),
            ("full_with_signal", FULL),
            ("hold_with_signal", REDUCED),
        ]
    }
    totals = {}
    for name, run in runs.items():
        triggered = name != "full_without_signal"
        s = run["selector_elapsed_seconds"]
        totals[name] = {
            "calls": run["calls"] + (triz["actual_sessions"] if triggered else 0),
            "wall_seconds": round(
                s + (triz["observed_parallel_wall_seconds"] if triggered else 0), 3
            ),
            "cumulative_session_seconds": round(
                s + (triz["sum_role_seconds"] if triggered else 0), 3
            ),
            "tokens": {
                k: run["tokens"][k] + (triz["tokens"][k] if triggered else 0)
                for k in USAGE
            },
            "usd": None,
        }
    return {
        "selector_runs": runs,
        "signal_generation": {
            k: triz[k]
            for k in [
                "actual_sessions",
                "sum_role_seconds",
                "observed_parallel_wall_seconds",
                "tokens",
                "known_usd",
            ]
        },
        "comparable_totals": totals,
        "hold_minus_full_including_signal_acquisition": {
            name: compare_costs(totals["hold_with_signal"], totals[name])
            for name in ["full_without_signal", "full_with_signal"]
        },
        "scope": "Observed selector elapsed includes CLI overhead/repairs. Sequential stage durations plus observed parallel TRIZ batch wall time are stage-summed critical-path estimates, not single end-to-end stopwatch readings. Shared A0, B, C/source acquisition, human review and unmetered authoring/orchestration excluded; differential human time and signed-in subscription USD are unknown. Output reasoning tokens are a subset of output tokens.",
    }


def score():
    assert COMMIT.is_file()
    ranking = commit()
    reference = load(REFERENCE)
    c = ranking["arms"]
    refitems = {r["item_id"]: r for r in reference["items"]}
    assert reference["case"] == CASE
    assert set(refitems) == set(c["hold_with_signal"]["rank_nonmandatory"]) | set(
        c["hold_with_signal"]["mandatory"]
    )
    major = {i for i, r in refitems.items() if r["grade"] == "중대 쟁점"}
    other = {
        i for i, r in refitems.items() if r["grade"] in ["수용 가능", "비중대 쟁점"]
    }
    pending = {i for i, r in refitems.items() if r["grade"] == "판정 유보"}
    assert set(refitems) == major | other | pending
    held = fixed_inputs()
    spec = next(r for r in cases() if r["case_id"].startswith(CASE + "-"))
    pages = prepare(spec)["pages"]
    verify({"items": [refitems[k] for k in held]}, held, pages)
    scores = {k: measure(v, major, other, pending) for k, v in c.items()}
    allocation = {}
    for arm in ["full_without_signal", "full_with_signal"]:
        allocation[arm] = {}
        for metric in ["fixed_k", "operational"]:
            original = set(c[arm][metric])
            modified = set(c["hold_with_signal"][metric])
            allocation[arm][metric] = {
                "previously_caught_major_lost": sorted(major & (original - modified)),
                "new_major_caught": sorted(major & (modified - original)),
                "newly_missed_pending": sorted(pending & (original - modified)),
                "change_in_number_of_missed_majors": len(major - modified)
                - len(major - original),
            }
    report = {
        "case": CASE,
        "scope": "Exploratory isolated Codex proxy, one enterprise and two targeted J2 items.",
        "ranking_commit_sha256": sha(COMMIT),
        "reference": relative(REFERENCE),
        "reference_sha256": sha(REFERENCE),
        "reference_mtime_utc": datetime.fromtimestamp(
            REFERENCE.stat().st_mtime, UTC
        ).isoformat(),
        "rank_commit_utc": ranking["frozen_utc"],
        "score_utc": utc(),
        "held_references": {k: refitems[k] for k in held},
        "reference_totals": {
            "major": len(major),
            "other": len(other),
            "pending": len(pending),
        },
        "graded_arms": scores,
        "miss_changes_hold_minus_full": allocation,
        "selector_rows": {k: v["selector_row_count"] for k, v in c.items()},
        "mandatory_all_retained": all(
            not (set(held) & set(v["mandatory"])) for v in c.values()
        ),
        "cost": costs(),
        "scientific_H2_eligible": False,
        "enable_operational_holds": False,
        "gate": "Official Terra H1/development prerequisite unmet; a single proxy case cannot establish the safety threshold, monetary savings or human review time. Two accepted J2 product overlaps do not establish issuer-wide valuation comparability.",
        "three_reviews": [
            {
                "round": 1,
                "check": "Outcome-blind hold freeze, 12 role tests and mandatory exemption.",
                "remedy": "Only two agreed camera-product facts passed both role-specific invariance and directional gates. Excluded three other dual accepts.",
            },
            {
                "round": 2,
                "check": "Shared selector contract, grade-free inputs, row partition and append order; frozen ranks before grade access.",
                "remedy": "Paired same-signal full arm controls for signal acquisition. Retained common sources, budget and page catalog; held rows appended using full L3 keys.",
            },
            {
                "round": 3,
                "check": "Every held reference, pending bounds, serious/other denominator, baseline delta and complete trial usage.",
                "remedy": "Report undefined recall/concordance as null when no qualifying items; price and human minutes remain unknown. Show parallel wall and cumulative session times separately.",
            },
        ],
    }
    dump(HERE / "audit.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["run", "commit", "score"])
    step = parser.parse_args().step
    {"run": selector_run, "commit": commit, "score": score}[step]()
