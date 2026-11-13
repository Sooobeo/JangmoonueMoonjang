"""Common v2 arithmetic, with source and immutable snapshot provenance.

Both policies call these same functions. Selection and coverage are caller
declarations; a successful calculation does not certify their factual accuracy.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import re

from .calculations import sensitivity as legacy_sensitivity
from .provenance import ContractError, SnapshotStore, decimal_text, unique_evidence
from .schemas_v2 import CALCULATION_TYPES


def _id(snapshot_id, name, entity=None):
    suffix = hashlib.sha256(str(entity or "issuer").encode("utf-8")).hexdigest()[:8]
    safe_name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if safe_name != name or len(safe_name) > 70:
        safe_name = safe_name[:50] + "_" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return "C_" + snapshot_id.removeprefix("X_") + "_" + safe_name + "_" + suffix


def _row(logical, name, formula, inputs, unit, result=None, status="OK", reason=None, entity=None, **extra):
    role_map = {
        "share_count_difference": ["derived_share_count", "reported_share_count"],
        "peer_market_cap": ["reference_price_krw", "reference_shares"],
        "peer_market_cap_difference": ["derived_market_cap_million_krw", "market_cap_million_krw"],
        "peer_recomputed_per": ["market_cap_million_krw", "earnings_million_krw"],
        "price_from_reported_equity": ["reported_equity_million_krw", "share_count"],
        "price_from_displayed_per": ["earnings_million_krw", "applied_per", "share_count"],
        "reported_price_difference": ["price_from_reported_equity", "reported_price_krw"],
        "displayed_price_difference": ["price_from_displayed_per", "reported_price_krw"],
        "implied_per": ["reported_equity_million_krw", "earnings_million_krw"],
        "price_from_recomputed_peer_mean": ["earnings_million_krw", "share_count"],
    }
    roles = role_map.get(name, [])
    if name.startswith("sensitivity_"):
        roles = ["earnings_million_krw", "applied_per", "share_count"]
    missing_ids, required, ambiguous = [], [], []
    for index, f in enumerate(inputs):
        if f is not None and f["value"] is None:
            missing_ids += f.get("missing_input_ids", [f["fact_id"]])
        if f is None:
            if index < len(roles):
                role = roles[index]
                matching_fields = {role}
                if role in {"share_count", "reported_share_count", "derived_share_count"}:
                    matching_fields |= {"share_count", "reported_share_count", "derived_share_count"}
                candidates = [candidate for candidate in logical["facts"].values() if candidate["entity_id"] == entity
                              and candidate["field"] in matching_fields and candidate["value"] is not None]
                label = (entity + "." if entity else "") + role
                if len(candidates) > 1:
                    ambiguous.append(label)
                    required.append(label + ".selection")
                else:
                    required.append(label)
            elif (name.startswith("peer_") or name.startswith("sensitivity_")) and logical["peers"]:
                peer_index = index - 3 if name.startswith("sensitivity_") else index
                if 0 <= peer_index < len(logical["peers"]):
                    required.append(logical["peers"][peer_index]["peer_id"] + ".per")
    if name == "share_sum":
        if not logical["share_components"]:
            required.append("share_components")
        if not logical["coverage"] or logical["coverage"][0]["coverage_status"] != "COMPLETE":
            required.append("coverage_status")
        required += [c["component_id"] + ".denominator_treatment" for c in logical["share_components"] if c["denominator_treatment"] == "UNRESOLVED"]
    if name.startswith("peer_") and not logical["peers"]:
        required.append("peers")
    facts = []
    for fact in inputs:
        if fact is not None and fact["fact_id"] not in {f["fact_id"] for f in facts}:
            facts.append(deepcopy(fact))
    return {"calc_id": _id(logical["input_snapshot_id"], name, entity), "id": name,
            "input_snapshot_id": logical["input_snapshot_id"], "entity_id": entity,
            "input_fact_ids": list(dict.fromkeys(fid for f in facts for fid in f.get("source_fact_ids", [f["fact_id"]]))),
            "operand_fact_ids": [f["fact_id"] for f in facts], "inputs": facts,
            "formula": formula, "result": result, "unit": unit, "status": status,
            "reason": ("Explicit SELECTION required for " + ", ".join(ambiguous)) if ambiguous and status != "OK" else reason,
            "missing_input_ids": list(dict.fromkeys(missing_ids)), "required_fields": list(dict.fromkeys(required)),
            "selection_required": bool(ambiguous),
            "evidence": unique_evidence([ev for f in facts for ev in f["evidence"]]),
            "precision": {"decimal_digits": 40, "rounding": "ROUND_HALF_EVEN"}, **extra}


def _selected(logical, field, entity=None, aliases=()):
    # A role-specific choice is authoritative, including an explicit unresolved
    # choice. Alias selections preserve their own disclosed/derived values and
    # must not override or render the caller's exact-role decision ambiguous.
    exact = [s for s in logical["selections"] if s["entity_id"] == entity and s["field"] == field]
    if exact:
        return logical["facts"].get(exact[0]["selected_fact_id"]) if len(exact) == 1 else None
    candidates = [s for s in logical["selections"] if s["entity_id"] == entity and s["field"] in aliases]
    if len(candidates) > 1:
        return None
    if candidates:
        return logical["facts"].get(candidates[0]["selected_fact_id"])
    candidates = [f for f in logical["facts"].values() if f["entity_id"] == entity and f["field"] in (field, *aliases)]
    # A missing original does not disqualify a single available derivation.
    usable = [f for f in candidates if f["value"] is not None]
    return usable[0] if len(usable) == 1 else candidates[0] if len(candidates) == 1 else None


def _problem(facts, *, positive=True):
    if any(f is None or f["value"] is None for f in facts):
        return "UNAVAILABLE", "Required inputs are absent, unresolved, or need an explicit selection"
    if positive and any(Decimal(f["value"]) <= 0 for f in facts):
        return "INVALID", "PER valuation inputs must be positive"
    return None


def _compatible(facts, *, dates=False):
    if any(f is None for f in facts):
        return "Required input is absent"
    for key in ("entity_id", "scope", "basis", "source_snapshot_id") + (("as_of",) if dates else ()):
        if len({f[key] for f in facts}) != 1:
            return "Declared input contexts are incompatible: " + key
    return None


def _formula(logical, name, formula, inputs, unit, calculate, entity=None, dates=False, positive=True, **extra):
    problem = _problem(inputs, positive=positive)
    if problem:
        return _row(logical, name, formula, inputs, unit, status=problem[0], reason=problem[1], entity=entity, **extra)
    mismatch = _compatible(inputs, dates=dates)
    if mismatch:
        return _row(logical, name, formula, inputs, unit, status="INVALID", reason=mismatch, entity=entity, **extra)
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_EVEN
        result = calculate(*[Decimal(f["value"]) for f in inputs])
    return _row(logical, name, formula, inputs, unit, result=decimal_text(result), entity=entity, **extra)


def _from_calculation(row, field, template, *, entity=None):
    """An internal derived input, retained inside subsequent calculation rows."""
    if template is None:
        return None
    return {**deepcopy(template), "fact_id": "F_" + row["calc_id"], "claim_id": "CLAIM_" + row["calc_id"],
            "field": field, "entity_id": entity, "value": row["result"], "unit": row["unit"],
            "origin": "DERIVED", "derivation_id": row["calc_id"], "evidence": deepcopy(row["evidence"]),
            "missing_reason": row["reason"], "input_snapshot_id": row["input_snapshot_id"],
            "source_fact_ids": list(row["input_fact_ids"]), "missing_input_ids": list(row["missing_input_ids"])}


def _share_rows(logical):
    components, facts = logical["share_components"], logical["facts"]
    included = [c for c in components if c["denominator_treatment"] == "INCLUDE"]
    inputs = [facts[c["fact_id"]] for c in included]
    with localcontext() as context:
        context.prec = 40
        partial = sum((Decimal(f["value"]) for f in inputs if f["value"] is not None), Decimal(0))
    complete = (bool(components) and len(logical["coverage"]) == 1 and logical["coverage"][0]["coverage_status"] == "COMPLETE"
                and not any(c["denominator_treatment"] == "UNRESOLVED" for c in components)
                and all(f["value"] is not None for f in inputs))
    mismatch = _compatible(inputs, dates=True) if inputs else "No included denominator components"
    status = "INVALID" if complete and mismatch else "OK" if complete else "UNAVAILABLE"
    reason = mismatch if status == "INVALID" else None if status == "OK" else "Coverage or denominator treatment/quantity is incomplete"
    row = _row(logical, "share_sum", "sum(INCLUDE quantities); excluded components do not increase denominator",
               inputs, "주", result=decimal_text(partial) if status == "OK" else None, status=status, reason=reason,
               partial_sum=decimal_text(partial), component_ids=[c["component_id"] for c in included],
               coverage=deepcopy(logical["coverage"]))
    reported = _selected(logical, "reported_share_count", aliases=("share_count",))
    derived = _from_calculation(row, "derived_share_count", inputs[0] if inputs else None)
    difference = _formula(logical, "share_count_difference", "derived_share_count - reported_share_count",
                          [derived, reported], "주", lambda a, b: a - b, dates=True, positive=False)
    return [row, difference]


def _peer_rows(logical):
    rows, recomputed, displayed = [], [], []
    for peer in logical["peers"]:
        entity = peer["peer_id"]
        facts = logical["facts"]
        price = facts.get(peer["reference_price_fact_id"])
        shares = facts.get(peer["reference_shares_fact_id"])
        reported_cap = facts.get(peer["market_cap_fact_id"])
        earnings = facts.get(peer["earnings_fact_id"])
        displayed.append(facts.get(peer["per_fact_id"]))
        cap = _formula(logical, "peer_market_cap", "reference_price_krw * reference_shares / 1000000",
                       [price, shares], "백만원", lambda p, s: p * s / Decimal(1000000), entity=entity, dates=True)
        rows.append(cap)
        derived_cap = _from_calculation(cap, "market_cap_million_krw", price, entity=entity)
        cap_selection = [s for s in logical["selections"] if s["entity_id"] == entity and s["field"] == "market_cap_million_krw"]
        if cap_selection:
            chosen = facts.get(cap_selection[0]["selected_fact_id"])
        elif reported_cap is not None and reported_cap["value"] is not None:
            # The same registered derived cap is not a second independent value.
            if reported_cap["origin"] == "DERIVED" or cap["status"] != "OK":
                chosen = reported_cap
            else:
                chosen = None
        else:
            chosen = derived_cap
        if reported_cap is not None and reported_cap["origin"] == "DISCLOSED" and derived_cap is not None:
            rows.append(_formula(logical, "peer_market_cap_difference", "derived_market_cap - disclosed_market_cap",
                                 [derived_cap, reported_cap], "백만원", lambda a, b: a - b, entity=entity, dates=True, positive=False))
        per = _formula(logical, "peer_recomputed_per", "selected_market_cap_million_krw / earnings_million_krw",
                       [chosen, earnings], "배", lambda cap_value, e: cap_value / e, entity=entity)
        if not cap_selection and reported_cap is not None and reported_cap["origin"] == "DISCLOSED" and reported_cap["value"] is not None and cap["status"] == "OK":
            per.update(selection_required=True,
                       reason="Explicit SELECTION required: both disclosed and derived market capitalizations are available",
                       required_fields=[entity + ".market_cap_million_krw.selection"])
        rows.append(per)
        recomputed.append(_from_calculation(per, "per", earnings, entity=entity))
    return rows, displayed, recomputed


def _aggregate(logical, name, facts, *, median=False):
    if not facts:
        return _row(logical, name, "median(peer.per)" if median else "sum(peer.per)/count(peers)", [], "배",
                    status="UNAVAILABLE", reason="No peers are registered")
    problem = _problem(facts)
    formula = "median(peer.per)" if median else "sum(peer.per)/count(peers)"
    if problem:
        return _row(logical, name, formula, facts, "배", status=problem[0], reason="No peer was silently dropped. " + problem[1])
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_EVEN
        numbers = sorted(Decimal(f["value"]) for f in facts)
        n = len(numbers)
        value = (numbers[n // 2] if n % 2 else (numbers[n // 2 - 1] + numbers[n // 2]) / Decimal(2)) if median else sum(numbers, Decimal(0)) / n
    return _row(logical, name, formula, facts, "배", result=decimal_text(value))


def evaluate(store: SnapshotStore, snapshot_id, calculation_types=None):
    types = ["ALL"] if calculation_types is None else calculation_types
    if not isinstance(types, list) or not types or any(t not in CALCULATION_TYPES for t in types):
        raise ContractError("Unknown calculation type")
    logical = store.logical(snapshot_id)
    requested = set(types)
    all_types = "ALL" in requested
    rows = []
    share_rows = _share_rows(logical)
    if all_types or "SHARE_SUM" in requested:
        rows.append(share_rows[0])
    if all_types or "SHARE_DIFFERENCE" in requested:
        rows.append(share_rows[1])
    peer_rows, displayed, recomputed = _peer_rows(logical)
    if all_types or requested & {"MARKET_CAP", "PER"}:
        rows += [r for r in peer_rows if all_types or ("MARKET_CAP" in requested and r["id"] != "peer_recomputed_per")
                 or ("PER" in requested and r["id"] == "peer_recomputed_per")]
    aggregates = [_aggregate(logical, "peer_displayed_mean", displayed),
                  _aggregate(logical, "peer_displayed_median", displayed, median=True),
                  _aggregate(logical, "peer_recomputed_mean", recomputed)]
    if all_types or "PEER_AGGREGATES" in requested:
        rows += aggregates
    if all_types or "PRICE" in requested:
        earnings = _selected(logical, "earnings_million_krw")
        multiple = _selected(logical, "applied_per")
        equity = _selected(logical, "reported_equity_million_krw")
        shares = _selected(logical, "share_count", aliases=("reported_share_count", "derived_share_count"))
        price = _selected(logical, "reported_price_krw")
        reported = _formula(logical, "price_from_reported_equity", "selected_equity_million_krw * 1000000 / selected_share_count",
                            [equity, shares], "원", lambda e, s: e * Decimal(1000000) / s, dates=True)
        displayed_price = _formula(logical, "price_from_displayed_per", "earnings_million_krw * applied_per * 1000000 / selected_share_count",
                                   [earnings, multiple, shares], "원", lambda e, p, s: e * p * Decimal(1000000) / s)
        rows += [reported, displayed_price,
                 _formula(logical, "reported_price_difference", "price_from_reported_equity - reported_price_krw",
                          [_from_calculation(reported, "reported_price_krw", equity), price], "원", lambda a, b: a - b, dates=True, positive=False),
                 _formula(logical, "displayed_price_difference", "price_from_displayed_per - reported_price_krw",
                          [_from_calculation(displayed_price, "reported_price_krw", earnings), price], "원", lambda a, b: a - b, positive=False),
                 _formula(logical, "implied_per", "reported_equity_million_krw / earnings_million_krw", [equity, earnings], "배", lambda a, b: a / b)]
        recomputed_mean = aggregates[-1]
        problem = _problem([earnings, shares])
        if recomputed_mean["status"] != "OK" or problem:
            rows.append(_row(logical, "price_from_recomputed_peer_mean", "earnings * 1000000 * recomputed_peer_mean / selected_share_count",
                             [earnings, shares, *[f for f in recomputed if f]], "원", status="UNAVAILABLE", reason="Required issuer or peer inputs are unavailable"))
        else:
            with localcontext() as context:
                context.prec = 40
                context.rounding = ROUND_HALF_EVEN
                value = Decimal(earnings["value"]) * Decimal(1000000) * Decimal(recomputed_mean["result"]) / Decimal(shares["value"])
            mismatch = _compatible([earnings, shares])
            rows.append(_row(logical, "price_from_recomputed_peer_mean", "earnings * 1000000 * recomputed_peer_mean / selected_share_count",
                             [earnings, shares, *recomputed], "원", result=decimal_text(value) if not mismatch else None,
                             status="INVALID" if mismatch else "OK", reason=mismatch))
    # Registered DERIVATIONs are also individually visible and remain tied to
    # the current snapshot, including invalid/unavailable outcomes.
    if all_types:
        for d in logical["derivations"]:
            rows.append(_row(logical, "derivation_" + d["derivation_id"], d["operation"],
                             [logical["facts"][fid] for fid in d["input_fact_ids"]], logical["facts"][d["output_fact_id"]]["unit"],
                             result=d["result"], status=d["status"], reason=d["reason"], entity=d["entity_id"],
                             output_fact_id=d["output_fact_id"]))
    return {"input_snapshot_id": snapshot_id, "calculations": rows,
            "notes": ["OK certifies arithmetic on the registered inputs, not source interpretation or coverage correctness.",
                      "Direct and derived observations and all rejected/unavailable calculations are retained."]}


def sensitivity(store: SnapshotStore, snapshot_id, alternatives=None):
    alternatives = ["MEAN", "MEDIAN", "LEAVE_ONE_OUT"] if alternatives is None else alternatives
    if not isinstance(alternatives, list) or not alternatives or set(alternatives) - {"MEAN", "MEDIAN", "LEAVE_ONE_OUT"}:
        raise ContractError("Unknown sensitivity alternative")
    logical = store.logical(snapshot_id)
    earnings = _selected(logical, "earnings_million_krw")
    multiple = _selected(logical, "applied_per")
    shares = _selected(logical, "share_count", aliases=("reported_share_count", "derived_share_count"))
    peers = [{"name": p["name"], "per": logical["facts"].get(p["per_fact_id"])} for p in logical["peers"]]
    def value(fact):
        return fact["value"] if fact else None
    result = legacy_sensitivity({"earnings_million_krw": value(earnings), "applied_per": value(multiple), "share_count": value(shares),
                                 "peers": [{"name": p["name"], "per": value(p["per"])} for p in peers]})
    inputs = [earnings, multiple, shares, *[p["per"] for p in peers]]
    mismatch = _compatible([f for f in (earnings, multiple, shares) if f])
    converted = []
    for row in [result["baseline"], *result["scenarios"]]:
        if row["id"] == "displayed_mean" and "MEAN" not in alternatives:
            continue
        if row["id"] == "displayed_median" and "MEDIAN" not in alternatives:
            continue
        if row["id"].startswith("exclude_peer_") and "LEAVE_ONE_OUT" not in alternatives:
            continue
        item = _row(logical, "sensitivity_" + row["id"], row["formula"], inputs, "원", result=row["result"],
                    status=row["status"], reason=row["reason"], assumption=row.get("assumption", "Displayed multiple baseline"))
        item.update({key: deepcopy(row[key]) for key in ("excluded_peer", "applied_per", "difference_krw", "difference_percent", "comparison_status", "comparison_reason") if key in row})
        if mismatch:
            item.update(result=None, status="INVALID", reason=mismatch, comparison_status="UNAVAILABLE", comparison_reason=mismatch,
                        difference_krw=None, difference_percent=None)
        converted.append(item)
    return {"input_snapshot_id": snapshot_id, "calculations": converted, "baseline": converted[0],
            "scenarios": converted[1:], "notes": result["notes"]}
