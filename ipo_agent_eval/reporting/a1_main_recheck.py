"""Read-only independent recomputation of the A1 main results from primary artifacts."""

import argparse
import hashlib
import itertools
import json
import math
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from statistics import fmean

from scipy.stats import ttest_1samp

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_main/v1"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"
ARMS = ("rule", "ai")
ACCEPT, MINOR, MATERIAL, PENDING = GRADES = (
    "수용 가능",
    "비중대 쟁점",
    "중대 쟁점",
    "판정 유보",
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def wire(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


class Crosscheck:
    def __init__(self):
        self.count = 0
        self.differences = []

    def compare(self, label, actual, expected):
        self.count += 1
        if (
            isinstance(expected, (list, tuple))
            and isinstance(actual, (list, tuple))
            and len(actual) == len(expected)
        ):
            for n, (a, e) in enumerate(zip(actual, expected)):
                self.compare(f"{label}[{n}]", a, e)
            return
        if isinstance(expected, float) and type(actual) in (float, int):
            match = math.isclose(actual, expected, abs_tol=1e-10, rel_tol=1e-11)
        else:
            match = actual == expected
        if not match:
            self.differences.append(
                {"source": label, "expected": expected, "reported": actual}
            )


def ledger(base, results, check):
    """Read attempt and outcome independently. A missing usage reconciles to its reserved ceiling."""
    path = base / "terra/ledger.sqlite3"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        reservations = list(db.execute("SELECT * FROM attempt ORDER BY id"))
        outcomes = {r["id"]: r for r in db.execute("SELECT * FROM outcome")}
        check.compare(
            "freeze/ledger",
            db.execute("SELECT hash FROM freeze").fetchone()[0],
            digest((base / "freeze.json").read_bytes()),
        )
    answers = {}
    attempts = Counter()
    known = []
    exposure = [0, 0]
    stages = defaultdict(list)
    for r in reservations:
        identifier, stage = r["id"], r["stage"]
        prefix = f"Terra/{identifier}"
        o = outcomes.get(identifier)
        check.compare(
            prefix + "/request_sha256", r["request_hash"], digest(r["request"])
        )
        attempts[r["receipt"], stage] += 1
        check.compare(prefix + "/ordinal", r["n"], attempts[r["receipt"], stage])
        known_usage = False
        if o is not None:
            check.compare(
                prefix + "/response_sha256", o["body_hash"], digest(o["body"])
            )
            try:
                body = json.loads(o["body"])
            except (TypeError, ValueError):
                body = {}
            body = body if isinstance(body, dict) else {}
            usage = body.get("usage") or {}
            usage = usage if isinstance(usage, dict) else {}
            pair = [usage.get(k) for k in ("input_tokens", "output_tokens")]
            known_usage = all(type(i) is int and i >= 0 for i in pair)
            check.compare(
                prefix + "/confirmed_usage",
                [o["input_n"], o["output_n"]],
                pair if known_usage else [None, None],
            )
            if known_usage:
                known.append(pair)
            if stage == "A1_SELECT" and body.get("status") == "completed":
                messages = [
                    c["text"]
                    for item in body.get("output", [])
                    if item["type"] == "message"
                    for c in item["content"]
                    if c["type"] == "output_text"
                ]
                try:
                    answers[identifier] = json.loads("".join(messages))["items"]
                except (TypeError, ValueError, KeyError):
                    pass
        for index, field in enumerate(("input_n", "output_n")):
            exposure[index] += o[field] if known_usage else r[field]
        stages[stage].append((r, o, known_usage))
    sums = [sum(pair[i] for pair in known) for i in (0, 1)]
    ceiling = (1.25 * exposure[0] + 5 * exposure[1]) / 1e6
    for k, v in {
        "attempts": len(reservations),
        "known_usage": len(known),
        "unknown_or_pending": len(reservations) - len(known),
        "known_standard_usd": (sums[0] + 5 * sums[1]) / 1e6,
        "accounted_ceiling_usd": ceiling,
    }.items():
        check.compare("cost/" + k, results["cost"][k], v)
    check.compare("Terra/request_cap", len(reservations) <= 444, True)
    check.compare("Terra/global_ceiling", ceiling <= 15, True)
    recorded = {r["stage"]: r for r in results["terra_by_stage"]}
    check.compare("Terra/stages", sorted(recorded), sorted(stages))
    for stage, rows in stages.items():
        valid = [o for _, o, v in rows if v]
        ended = [o for _, o, _ in rows if o is not None]
        values = {
            "sends": len(rows),
            "known_usage": len(valid),
            "timed_sends": len(ended),
            "input_tokens": sum(o["input_n"] for o in valid) if valid else None,
            "output_tokens": sum(o["output_n"] for o in valid) if valid else None,
            "service_seconds": sum(o["elapsed"] for o in ended) if ended else None,
            "noninitial_sends": sum(r["kind"] != "initial" for r, _, _ in rows),
        }
        for key, value in values.items():
            check.compare(
                f"Terra/{stage}/{key}", recorded.get(stage, {}).get(key), value
            )
    return answers


def allocations(op, registry, b, ranking, answers, check):
    check.compare("ranking/mandatory", ranking["mandatory"], b["mandatory"])
    common = b["mandatory"]
    optional = {r["id"] for r in registry} - set(common)
    merged = read(op / "merged.json")
    allowed = set(merged["sources"]) | {f"PDF-{r['pages'][0]}" for r in registry}
    native = {r["item_id"]: r for r in answers[ranking["decision_run"]]}
    check.compare(
        "ranking/all AI answers", sorted(native), sorted(r["id"] for r in registry)
    )
    scores = {arm: {} for arm in ARMS}
    eligible = {arm: set() for arm in ARMS}
    for row in merged["items"]:
        key = row["item_id"]
        if key not in optional:
            continue
        roles = (row["a0"], row["c"])
        challenge = any(
            r["state"] == "문제 제기" and set(r["evidence_ids"]) & allowed
            for r in roles
        )
        group = (
            0 if challenge else 1 if any(r["state"] == "미확인" for r in roles) else 2
        )
        impact = b["price_impact_fraction"].get(key)
        scores["rule"][key] = (
            group,
            impact is None,
            -Decimal(str(impact)) if impact is not None else Decimal(0),
        )
        scores["ai"][key] = -native[key]["priority"]
        if challenge:
            eligible["rule"].add(key)
        if native[key]["action"] == "사람 검토":
            eligible["ai"].add(key)
    queues = {}
    for arm in ARMS:
        rows = ranking[arm]
        ids = sorted(scores[arm], key=lambda k: (scores[arm][k], k))
        selected = [k for k in ids if k in eligible[arm]]
        check.compare(
            f"ranking/{arm}/order", [r["item_id"] for r in rows["items"]], ids
        )
        check.compare(
            f"ranking/{arm}/eligible",
            [r["eligible"] for r in rows["items"]],
            [k in eligible[arm] for k in ids],
        )
        check.compare(f"ranking/{arm}/fixed", rows["fixed_k"], common + ids[:1])
        check.compare(f"ranking/{arm}/wait", rows["waiting"], selected[1:])
        check.compare(
            f"ranking/{arm}/operational", rows["operational"], common + selected[:1]
        )
        queues[arm] = {
            "rank": ids,
            "fixed": set(common + ids[:1]),
            "operating": common + selected[:1],
            "scores": scores[arm],
        }
    return queues


def independent_votes(folder, check):
    sealed = read(folder / "sealed.json")
    votes = []
    for phase in ("first", "second", "reconcile"):
        path = folder / phase / "accepted.json"
        if path.exists():
            votes.append(
                {r["item_id"]: r["grade"] for r in read(path)["answer"]["items"]}
            )
    first, second, *rest = votes
    disputed = {k for k in first if first[k] != second[k]}
    extra = rest[0] if rest else {}
    check.compare("reference/adjudicated IDs", sorted(extra), sorted(disputed))
    audit = (
        read(folder / "source_audit.json")
        if (folder / "source_audit.json").exists()
        else {}
    )
    derived = {}
    for key in first:
        group = [first[key], second[key]] + ([extra[key]] if key in disputed else [])
        grade, n = Counter(group).most_common(1)[0]
        result = grade if n >= 2 else PENDING
        if (key in disputed or result in (MATERIAL, PENDING)) and not audit[key][
            "supported"
        ]:
            result = PENDING
        derived[key] = result
    check.compare("reference/sealed grades", sealed["grades"], derived)
    return derived


def primary(scores, grades):
    material = [k for k in scores if grades[k] == MATERIAL]
    nonmaterial = [k for k in scores if grades[k] in (ACCEPT, MINOR)]
    wins = [
        (scores[m] < scores[n]) + 0.5 * (scores[m] == scores[n])
        for m, n in itertools.product(material, nonmaterial)
    ]
    return fmean(wins) if wins else None


def deferred_range(queues, grades):
    """A changed item's pairwise win contribution is the difference of its two midranks."""
    keys = list(queues["ai"]["scores"])
    differential = dict.fromkeys(keys, 0.0)
    for key in keys:
        for arm, sign in (("ai", 1), ("rule", -1)):
            score = queues[arm]["scores"]
            differential[key] += sign * sum(
                (score[key] < score[k]) + 0.5 * (score[key] == score[k]) for k in keys
            )
    fixed = [k for k in keys if grades[k] == MATERIAL]
    undecided = sorted(differential[k] for k in keys if grades[k] == PENDING)
    base = sum(differential[k] for k in fixed)
    values = []
    configurations = 0
    for n in range(len(undecided) + 1):
        positives = n + len(fixed)
        denominator = positives * (len(keys) - positives)
        if denominator:
            configurations += math.comb(len(undecided), n)
            for addition in (
                sum(undecided[:n]),
                sum(reversed(undecided[len(undecided) - n :])),
            ):
                values.append((base + addition) / denominator)
    return ([min(values), max(values)] if values else None), configurations


def case_metrics(row, queues, grades, check):
    material = {k for k in grades if grades[k] == MATERIAL}
    pending = {k for k in grades if grades[k] == PENDING}
    scores = {arm: primary(queues[arm]["scores"], grades) for arm in ARMS}
    delta = scores["ai"] - scores["rule"] if scores["ai"] is not None else None
    check.compare(
        row["case"] + "/primary", row["concordance_delta_ai_minus_rule"], delta
    )
    bounds, configurations = deferred_range(queues, grades)
    check.compare(
        row["case"] + "/shared unresolved bounds",
        row["concordance_delta_pending_bounds"],
        bounds,
    )
    check.compare(
        row["case"] + "/shared unresolved count",
        row["valid_pending_assignments"],
        configurations,
    )
    report = {
        "material": len(material),
        "items": len(grades),
        "delta": delta,
        "unresolved_range": bounds,
        "configurations": configurations,
        "curves": {},
        "miss": {},
        "found": {},
        "bounds": {},
        "transfers": {},
    }
    for arm in ARMS:
        actual = row[arm]["concordance"]
        check.compare(
            f"{row['case']}/{arm}/primary",
            actual["score"] if actual else None,
            scores[arm],
        )
        rank = queues[arm]
        report["transfers"][arm] = len(rank["operating"])
        report["curves"][arm] = [
            len((set(row["mandatory"]) | set(rank["rank"][:n])) & material)
            for n in range(len(rank["rank"]) + 1)
        ]
        for policy in ("fixed", "operating"):
            included = set(rank[policy])
            obs = row["fixed_k"][arm] if policy == "fixed" else row[arm]["operating"]
            found, missed = sorted(included & material), sorted(material - included)
            bound = [len(missed), len((material | pending) - included)]
            for label, value in (
                ("material_missed", missed),
                ("material_found", found),
                ("miss_count_bounds", bound),
            ):
                check.compare(
                    f"{row['case']}/{arm}/{policy}/{label}", obs[label], value
                )
            report["miss"][arm, policy], report["found"][arm, policy] = (
                len(missed),
                len(found),
            )
            report["bounds"][arm, policy] = bound
    newly = sorted(
        (set(queues["rule"]["operating"]) - set(queues["ai"]["operating"])) & material
    )
    check.compare(
        row["case"] + "/newly missed",
        row["operating_difference"]["newly_missed_by_ai"],
        newly,
    )
    report["newly_missed"] = newly
    return report


def cohort(name, expected_count, reports, obs, check):
    values = [r["delta"] for r in reports if r["delta"] is not None]
    variable = len(set(values)) > 1
    test = ttest_1samp(values, 0) if variable else None
    interval = list(map(float, test.confidence_interval())) if variable else None
    total = sum(r["material"] for r in reports)
    matched = [r["unresolved_range"] for r in reports if r["delta"] is not None]
    checks = {
        "expected_cases": expected_count,
        "complete_pairs": len(reports),
        "valid_concordance_pairs": len(values),
        "primary_equal_issuer_ai_minus_rule": fmean(values) if values else None,
        "known_material": total,
        "pending_bounds_on_primary_matched_cohort": [
            fmean(v[n] for v in matched) for n in (0, 1)
        ]
        if matched
        else None,
        "additional_valid_if_deferred_classified": sum(
            r["delta"] is None and r["configurations"] > 0 for r in reports
        ),
        "descriptive_95_t_interval": interval,
        "two_sided_p": float(test.pvalue) if variable else None,
        "rank_superiority": interval[0] > 0 if variable and len(values) >= 15 else None,
        "ai_newly_missed_material_items": [
            k for r in reports for k in r["newly_missed"]
        ],
    }
    for k, v in checks.items():
        check.compare(name + "/" + k, obs[k], v)
    for arm in ARMS:
        check.compare(
            name + "/" + arm + "/transfers",
            obs["operating"][arm]["transfers"],
            sum(r["transfers"][arm] for r in reports),
        )
        for mode in ("fixed", "operating"):
            obj = obs["fixed_same_k" if mode == "fixed" else "operating"][arm]
            missed = sum(r["miss"][arm, mode] for r in reports)
            check.compare(f"{name}/{arm}/{mode}/miss", obj["material_missed"], missed)
            check.compare(
                f"{name}/{arm}/{mode}/recall",
                obj["material_recall"],
                (total - missed) / total if total else None,
            )
            check.compare(
                f"{name}/{arm}/{mode}/bounds",
                obj["miss_count_bounds"],
                [sum(r["bounds"][arm, mode][i] for r in reports) for i in (0, 1)]
                if reports
                else None,
            )
        maximum = max((len(r["curves"][arm]) - 1 for r in reports), default=0)
        check.compare(
            name + "/curve range",
            sorted(map(int, obs["same_k_curve"])),
            list(range(1, maximum + 1)),
        )
        for k in range(1, maximum + 1):
            found = sum(
                r["curves"][arm][min(k, len(r["curves"][arm]) - 1)] for r in reports
            )
            curve = obs["same_k_curve"][str(k)][arm]
            check.compare(f"{name}/{arm}/curve/{k}/found", curve["found"], found)
            check.compare(
                f"{name}/{arm}/curve/{k}/denominator", curve["denominator"], total
            )


def persona(base, assignments, results, check):
    timeline = results["operational_review_timing"]
    order = sorted(
        {
            (c, i)
            for c, routes in assignments.items()
            for keys in routes.values()
            for i in keys or []
        },
        key=lambda pair: digest("/".join(pair).encode()),
    )
    allocation = base / "timing/assignments.json"
    check.compare("time/union", read(allocation)["order"], order)
    check.compare(
        "time/assignment digest",
        timeline["assignment_sha256"],
        digest(allocation.read_bytes()),
    )
    timed = {}
    missing = 0
    sessions = set()
    citations = 0
    for case, item in order:
        folder = base / "timing" / case / item
        pos = f"time/{case}/{item}"
        result = read(folder / "timing.json")
        trials = [read(path) for path in sorted(folder.glob("attempt-*/closed.json"))]
        check.compare(pos + "/max starts", len(trials) <= 2, True)
        check.compare(pos + "/starts", result["attempts"], len(trials))
        accepted = folder / "accepted.json"
        prepared = folder / "prepared.json"
        if trials:
            source = read(base / "issuers" / case / "grading.json")
            registry = read(base / "issuers" / case / "items.json")
            page_ids = next(r["pages"] for r in registry if r["id"] == item)
            question = next(
                r["question"] for r in source["items"] if r["item_id"] == item
            )
            packet = {
                "check_question": question,
                "original_physical_pages": {
                    str(n): source["pages"][str(n)] for n in page_ids
                },
            }
            request = read(folder / "request.json")
            check.compare(pos + "/neutral payload", request["input"] == packet, True)
            check.compare(
                pos + "/persona",
                digest(request["instructions"].encode()),
                "ef9baf7f16407e31199262ab169cfa09dc47ea49ca31f235d0ca1b51d9b2031b",
            )
            check.compare(
                pos + "/model",
                [request["model"], request["reasoning"]],
                ["gpt-6.2-astra", "medium"],
            )
            check.compare(
                pos + "/prepared digest",
                read(prepared)["packet_sha256"],
                digest(wire(packet)),
            )
            check.compare(
                pos + "/timed digest", result["packet_sha256"], digest(wire(packet))
            )
            for n, r in enumerate(trials, 1):
                outbound = folder / f"attempt-{n}" / "outbound.txt"
                if outbound.exists():
                    check.compare(
                        pos + f"/{n}/wire",
                        digest(outbound.read_bytes()),
                        digest(request["instructions"].encode() + b"\n" + wire(packet)),
                    )
                for s in r.get("sessions", []):
                    check.compare(pos + "/unique session", s not in sessions, True)
                    sessions.add(s)
            if accepted.exists():
                rec = read(accepted)
                check.compare(pos + "/isolated", rec["tool_events"], [])
                for cite in rec["answer"]["citations"]:
                    excerpt = "".join(cite["quote"].split())
                    original = packet["original_physical_pages"].get(
                        str(cite["physical_page"]), ""
                    )
                    check.compare(
                        pos + "/exact source quote",
                        len(excerpt) >= 6 and excerpt in "".join(original.split()),
                        True,
                    )
                    citations += 1
        valid = accepted.exists()
        known = (
            valid
            and bool(trials)
            and all(r["elapsed_seconds"] is not None for r in trials)
        )
        expected = (
            read(prepared)["packet_prep_seconds"]
            + sum(r["elapsed_seconds"] for r in trials)
            if known
            else None
        )
        check.compare(pos + "/whole", result["whole_seconds"], expected)
        check.compare(pos + "/valid", result["valid_review"], valid)
        for field, entry in (
            ("service_seconds", "session_seconds"),
            ("verification_seconds", "verification_seconds"),
        ):
            check.compare(
                pos + "/" + field,
                result[field],
                sum(r.get(entry, 0) for r in trials) if known else None,
            )
        timed[case, item] = expected
        missing += expected is None
    check.compare(
        "time/unique assigned", timeline["unique"]["assigned_items"], len(order)
    )
    check.compare(
        "time/unique measured", timeline["unique"]["timed_items"], len(order) - missing
    )
    matched = []
    combined = Counter()
    for case, routes in assignments.items():
        durations = {}
        for arm, items in routes.items():
            reported = timeline["per_case"][case][arm]
            if items is None:
                check.compare(f"time/{case}/{arm}/unknown", reported, None)
                continue
            observations = [timed[case, k] for k in items]
            durations[arm] = (
                sum(observations) if all(s is not None for s in observations) else None
            )
            check.compare(
                f"time/{case}/{arm}/whole", reported["whole_seconds"], durations[arm]
            )
            check.compare(
                f"time/{case}/{arm}/measured",
                reported["timed_items"],
                sum(s is not None for s in observations),
            )
        if set(durations) == set(ARMS) and all(
            s is not None for s in durations.values()
        ):
            matched.append(case)
            combined.update(durations)
    check.compare("time/paired cohorts", timeline["paired_complete_issuers"], matched)
    check.compare(
        "time/paired delta",
        timeline["paired_delta_seconds_ai_minus_rule"],
        combined["ai"] - combined["rule"] if matched else None,
    )
    return {
        "assigned": len(order),
        "observed": len(order) - missing,
        "missing": missing,
        "cited_passages": citations,
    }


def recheck(base, roster):
    check = Crosscheck()
    result_file = base / "analysis/results.json"
    results = read(result_file)
    freeze = read(base / "freeze.json")
    rows = read(roster)["rows"]
    expected_ids = [r["receipt"] for r in rows]
    check.compare("frozen roster", freeze["roster_sha256"], digest(roster.read_bytes()))
    check.compare("roster population", len(expected_ids), 37)
    check.compare("cohort order", [r["case"] for r in results["issuers"]], expected_ids)
    answers = ledger(base, results, check)
    reports = {}
    routes = {}
    states = Counter()
    confusion = Counter()
    agreement_cases = []
    for row, src in zip(results["issuers"], rows):
        case = src["receipt"]
        issuer = base / "issuers" / case
        op = base / "terra" / case
        blind = base / "blind" / case
        check.compare(
            case + "/preparation", row["preparation"], freeze["issuers"][case]
        )
        check.compare(case + "/role_a0", row["role_a0"], (op / "A0.json").exists())
        check.compare(case + "/role_c", row["role_c"], (op / "C.json").exists())
        check.compare(case + "/issuer", row["issuer"], src["issuer"])
        originals = [blind / phase / "accepted.json" for phase in ("first", "second")]
        if all(path.is_file() for path in originals):
            first, second = (
                {r["item_id"]: r["grade"] for r in read(path)["answer"]["items"]}
                for path in originals
            )
            check.compare(case + "/initial populations", sorted(first), sorted(second))
            agreement_cases.append(case)
            confusion.update((first[k], second[k]) for k in first)
        grades = None
        if (blind / "sealed.json").exists():
            grades = independent_votes(blind, check)
            grade_state = "sealed"
        elif not freeze["issuers"][case]["grading_ready"]:
            grade_state = "preparation_incomplete"
        else:
            grade_state = "outstanding"
            for phase in ("first", "second", "reconcile"):
                tries = [read(p) for p in (blind / phase).glob("attempt-*/closed.json")]
                if len(tries) == 2 and not any(r["valid"] for r in tries):
                    grade_state = phase + "_failed"
                    break
        check.compare(case + "/grade state", row["grade_state"], grade_state)
        if (op / "ranking.json").exists():
            ranking = read(op / "ranking.json")
            qs = allocations(
                op,
                read(issuer / "items.json"),
                read(issuer / "b.json"),
                ranking,
                answers,
                check,
            )
            routes[case] = {arm: qs[arm]["operating"] for arm in ARMS}
            selected = "ranked"
            if grades is not None:
                reports[case] = case_metrics(row, qs, grades, check)
        else:
            artifact = next(
                (
                    op / n
                    for n in ("failure.json", "preparation.json")
                    if (op / n).exists()
                ),
                None,
            )
            if artifact is None:
                raise ValueError(f"{case}: selection pending")
            selected = read(artifact)
            if selected["fallback"] == "rule":
                fallback = read(op / "rule.json")["operational"]
            else:
                fallback = (
                    read(issuer / "b.json")["mandatory"]
                    if (issuer / "b.json").exists()
                    else None
                )
            check.compare(case + "/fallback", selected["operational"], fallback)
            routes[case] = {"fallback": fallback}
        check.compare(case + "/selection", row["selection_state"], selected)
        check.compare(
            case + "/pair status",
            row["status"],
            "COMPARED" if case in reports else "INCOMPLETE",
        )
        states[
            grade_state, "ranked" if selected == "ranked" else selected["fallback"]
        ] += 1
    cf = {(a, b): n for a, b, n in results["pre_adjudication_cross_table"]}
    check.compare(
        "reference/confusion",
        sorted((a, b, n) for (a, b), n in cf.items() if n),
        sorted((a, b, n) for (a, b), n in confusion.items() if n),
    )
    n = sum(confusion.values())
    check.compare(
        "reference/agreement cohorts", results["agreement_cases"], agreement_cases
    )
    check.compare("reference/agreement N", results["agreement_denominator"], n)
    check.compare(
        "reference/agreement",
        results["exact_grade_agreement"],
        sum(confusion[g, g] for g in GRADES) / n if n else None,
    )
    cohort("all", len(rows), list(reports.values()), results["overall"], check)
    subset = [r["receipt"] for r in rows if r["issuer"] != "워트"]
    cohort(
        "excluding_wort",
        len(subset),
        [reports[c] for c in subset if c in reports],
        results["excluding_wort"],
        check,
    )
    times = persona(base, routes, results, check)
    for group in ("blind", "timing"):
        records = [read(p) for p in (base / group).glob("*/*/attempt-*/closed.json")]
        tokens = Counter()
        used = 0
        for r in records:
            if len(r.get("usage", [])) == 1:
                used += 1
                tokens.update(r["usage"][0])
        expected = {
            "sessions_started": len(records),
            "valid_sessions": sum(r["valid"] for r in records),
            "sessions_with_usage": used,
            "usage": {k: v for k, v in tokens.items() if v},
            "cost": None,
        }
        check.compare(group + "/sessions", results["codex"][group], expected)
    return {
        "checks": check.count,
        "differences": check.differences,
        "pairs": len(reports),
        "timing": times,
        "flow": [
            {"grade": a, "selection": b, "issuers": n}
            for (a, b), n in sorted(states.items())
        ],
        "results_sha256": digest(result_file.read_bytes()),
        "freeze_sha256": digest((base / "freeze.json").read_bytes()),
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--base", type=Path, default=BASE)
    cli.add_argument("--roster", type=Path, default=ROSTER)
    cli.add_argument(
        "--record",
        action="store_true",
        help="save independent_recheck.json after a successful check",
    )
    args = cli.parse_args()
    result = recheck(args.base, args.roster)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["differences"]:
        raise SystemExit(1)
    if args.record:
        path = args.base / "analysis/independent_recheck.json"
        data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Independent verification artifact changed")
        else:
            with path.open("xb") as handle:
                handle.write(data)


if __name__ == "__main__":
    main()
