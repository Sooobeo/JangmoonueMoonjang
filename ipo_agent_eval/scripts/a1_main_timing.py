"""Allocate each distinct operational review once, with route information kept local."""

from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once


def freeze_assignments(cases):
    rows = {}
    assignments = set()
    mandatory_count = 0
    for case in cases:
        folder = BASE / "terra" / case
        frozen_b = BASE / "issuers" / case / "b.json"
        common = read(frozen_b)["mandatory"] if frozen_b.is_file() else []
        mandatory_count += len(common)
        rank = folder / "ranking.json"
        if rank.exists():
            raw = rank.read_bytes()
            data = read(rank)
            routes = {arm: data[arm]["operational"] for arm in ("rule", "ai")}
            if data["mandatory"] != common:
                raise ValueError("Ranking changed the frozen mandatory list: " + case)
        else:
            fallback = next(
                (
                    folder / n
                    for n in ("failure.json", "preparation.json")
                    if (folder / n).exists()
                ),
                None,
            )
            if fallback is None:
                raise ValueError(case + " selection outstanding")
            raw = fallback.read_bytes()
            routes = {"fallback": read(fallback)["operational"]}
        for keys in routes.values():
            if keys is None and not common:
                continue
            if (
                keys is None
                or len(keys) != len(set(keys))
                or not set(common).issubset(keys)
                or len(set(keys) - set(common)) > 1
            ):
                raise ValueError("Invalid operational timing allocation: " + case)
            assignments.update((case, k) for k in keys)
        rows[case] = {"source_sha256": hash_bytes(raw), "routes": routes}
    order = sorted(assignments, key=lambda x: hash_bytes("/".join(x).encode()))
    if len(order) > mandatory_count + 2 * len(cases):
        raise ValueError("Timing assignment cap exceeded")
    record = {
        "cases": rows,
        "order": order,
        "count": len(order),
        "mandatory_total": mandatory_count,
        "max_jobs": mandatory_count + 2 * len(cases),
    }
    write_once(BASE / "timing/assignments.json", wire(record))
    return record


def summary(cases):
    allocation = freeze_assignments(cases)
    metrics = (
        "packet_prep_seconds",
        "service_seconds",
        "verification_seconds",
        "whole_seconds",
    )
    observed = {}
    for case, item in allocation["order"]:
        path = BASE / "timing" / case / item / "timing.json"
        if not path.is_file():
            raise ValueError(f"{case}/{item} timing outstanding")
        observed[(case, item)] = read(path)

    def totals(keys):
        known = [
            observed[key] for key in keys if observed[key]["whole_seconds"] is not None
        ]
        return {
            "assigned_items": len(keys),
            "timed_items": len(known),
            "missing_items": [
                {"case": c, "item": k, "reason": observed[c, k]["missing_reason"]}
                for c, k in keys
                if observed[c, k]["whole_seconds"] is None
            ],
            "observed_sums": {
                metric: sum(r[metric] for r in known) for metric in metrics
            },
            "whole_seconds": sum(r["whole_seconds"] for r in known)
            if len(keys) == len(known)
            else None,
        }

    per_case = {}
    matched_cases = []
    for case, entry in allocation["cases"].items():
        routes = entry["routes"]
        case_result = {
            arm: totals([(case, k) for k in keys]) if keys is not None else None
            for arm, keys in routes.items()
        }
        per_case[case] = case_result
        if "ai" in routes and all(
            v["whole_seconds"] is not None for v in case_result.values()
        ):
            matched_cases.append(case)
    comparison = {
        arm: sum(per_case[c][arm]["whole_seconds"] for c in matched_cases)
        for arm in ("ai", "rule")
    }
    return {
        "assignment_sha256": hash_bytes(
            (BASE / "timing/assignments.json").read_bytes()
        ),
        "unique": totals(allocation["order"]),
        "per_case": per_case,
        "paired_complete_issuers": matched_cases,
        "paired_issuer_count": len(matched_cases),
        "paired_proxy_seconds": comparison if matched_cases else None,
        "paired_delta_seconds_ai_minus_rule": comparison["ai"] - comparison["rule"]
        if matched_cases
        else None,
        "human_seconds": None,
    }
