"""Recalculate the two descriptive cohorts registered when the masking incident was found."""
from argparse import ArgumentParser
from pathlib import Path

from scripts.a1_main_analysis import infer
from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once


def summarize(audited):
    result = BASE/"analysis/results.json"
    rows = read(result)["issuers"]
    evidence = read(audited)
    exposure = {r["case"]: r for r in evidence["rows"]}
    if set(exposure) != {r["case"] for r in rows}:
        raise ValueError("Actual outbound masking audit must cover every registered issuer")
    for r in exposure.values():
        for key in ("direct_self_or_issuer", "direct_third_party"):
            if type(r[key]) is not bool:
                raise ValueError("Actual exposure must be classified before the supplemental analysis")
    own = {case for case, r in exposure.items() if r["direct_self_or_issuer"]}
    any_direct = own | {case for case, r in exposure.items() if r["direct_third_party"]}
    output = {
        "results_sha256": hash_bytes(result.read_bytes()),
        "operative_audit_sha256": hash_bytes(audited.read_bytes()),
        "decision_sha256": hash_bytes((BASE/"corrections/c_identity/판단규칙.md").read_bytes()),
        "self_exposed": len(own), "self_exposed_cases": sorted(own),
        "any_direct_exposed": len(any_direct), "any_direct_exposed_cases": sorted(any_direct),
        "without_self": infer([r for r in rows if r["case"] not in own]),
        "without_any_direct": infer([r for r in rows if r["case"] not in any_direct]),
    }
    write_once(BASE/"analysis/identity_sensitivity.json",wire(output))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    summarize(parser.parse_args().audit)
