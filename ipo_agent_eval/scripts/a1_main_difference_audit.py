"""Build the citation review for items on different locked K=1 or operating lists."""
from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once


def compare(case):
    op = BASE / "terra" / case
    ranking = read(op / "ranking.json")
    grade_file = BASE / "blind" / case / "sealed.json"
    grades = read(grade_file)
    merged = read(op / "merged.json")
    catalog = read(BASE / "issuers" / case / "catalog.json")["pages"]
    item_rows = {row["item_id"]: row for row in merged["items"]}
    actions = {row["item_id"]: row for row in ranking["ai"]["items"]}
    roles = {name: set(ranking[name]["operational"]) for name in ("rule", "ai")}
    fixed = {name: set(ranking[name]["fixed_k"]) for name in ("rule", "ai")}
    keys = (roles["rule"] ^ roles["ai"]) | (fixed["rule"] ^ fixed["ai"])
    rows = {}
    for key in sorted(keys):
        item = item_rows[key]
        decision = actions[key]
        refs = set(decision["evidence_ids"]) | set(item["a0"]["evidence_ids"]) | set(item["c"]["evidence_ids"])
        evidence = {}
        for ref in sorted(refs):
            if ref in merged["sources"]:
                evidence[ref] = merged["sources"][ref]
            elif ref in ranking["presented_refs"] and ref.startswith("PDF-"):
                evidence[ref] = catalog[ref.removeprefix("PDF-")]
            else:
                raise ValueError(f"Cannot replay a cited source in {key}: {ref}")
        rows[key] = {
            "question": item["question"], "a0": item["a0"], "c": item["c"], "ai": decision,
            "cited_sources": evidence, "grade": grades["grades"][key],
            "grade_evidence": grades["reference"]["items"][key],
            "on_lists": {n: [a for a in ("rule", "ai") if key in m[a]]
                         for n, m in (("fixed_k", fixed), ("operating", roles))},
        }
    return {"case": case, "ranking_sha256": hash_bytes((op / "ranking.json").read_bytes()),
            "sealed_grades_sha256": hash_bytes(grade_file.read_bytes()), "items": rows}


def main():
    # The final results file is written only after every selection and grading path is terminal.
    result = read(BASE / "analysis/results.json")
    cases = [r["case"] for r in result["issuers"] if r["status"] == "COMPARED"]
    for case in cases:
        write_once(BASE / "analysis/citation_review" / case / "packet.json", wire(compare(case)))
    print(f"Locked comparison packets: {len(cases)}")


if __name__ == "__main__":
    main()
