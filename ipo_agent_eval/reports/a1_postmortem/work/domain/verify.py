"""Independent audit of the domain evidence table, frozen referrals and cited PDF evidence."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import fitz


out = Path(__file__).resolve().parent
source = out.parents[2] / "a1_main" / "v1"
pdf_dir = out.parents[2] / "a1_current" / "official" / "enrollment_expansion" / "filings_source"
summary = json.loads((out / "domain_counts.json").read_bytes())
data = {row["item"]: row for row in summary["item_rows"]}
assert len(data) == 406
roles = Counter()
for case in summary["cases"]:
    case_id = case["case"]
    if not case["paired"]:
        continue
    rank = json.loads((source / "terra" / case_id / "ranking.json").read_bytes())
    grade = json.loads((source / "blind" / case_id / "sealed.json").read_bytes())["grades"]
    assert not rank["mandatory"]
    for arm in ("rule", "ai"):
        selected = set(rank[arm]["operational"])
        for item, label in grade.items():
            assert (item in selected) == data[item][arm]
            assert (label == "중대 쟁점") == (data[item]["grade"] == "material")
            roles["membership_checks"] += 1
            if item in selected:
                roles[arm] += 1
                if label == "중대 쟁점":
                    roles[arm + "_material"] += 1
assert roles == dict(membership_checks=582, rule=23, ai=26, rule_material=2, ai_material=3)

anchors = {
    "20230818000362": {223: ["한독", "의료기기"], 228: ["27.61", "38.14", "23.57", "21.13"], 256: ["88.1"]},
    "20250328002012": {222: ["KOBELCOWIRE", "8.06", "5미만", "PER10배미만"], 226: ["11.55"]},
    "20230918000204": {185: ["54.4", "43.0", "97.6"], 188: ["18.28", "46.12", "4.28", "7.35"], 213: ["98.9"]},
    "20251223000517": {279: ["3,901,797,615", "5,202,396,820"], 374: ["3,185,024,840", "375,381,280"]},
    "20250325000608": {175: ["37.62", "12.07"], 184: ["20.99"]},
    "20240621000553": {252: ["6,872"], 348: ["562,121"]},
    "20230912000404": {174: ["92.77", "49.65"], 180: ["23.19"], 209: ["63.37"]},
}
pdf_markers = []
for case, pages in anchors.items():
    with fitz.open(pdf_dir / (case + ".pdf")) as pdf:
        for page, terms in pages.items():
            content = "".join(pdf[page - 1].get_text().split())
            for term in terms:
                assert term in content, (case, page, term)
            pdf_markers.append({"case": case, "page": page, "verified_terms": terms})
report = (out / "evidence.md").read_text(encoding="utf-8")
local_links = []
for _, url in re.findall(r"\[([^]]+)\]\(([^)]+)\)", report):
    if not urlsplit(url).scheme:
        dest = out / unquote(url)
        if dest.name != "verification.json":
            assert dest.is_file(), str(dest)
        local_links.append(url)
check = {
    "operational_membership": roles, "local_links": sorted(set(local_links)),
    "pdf_markers": pdf_markers,
    "frozen_results_sha256": hashlib.sha256((source / "analysis" / "results.json").read_bytes()).hexdigest(),
    "counts_file_sha256": hashlib.sha256((out / "domain_counts.json").read_bytes()).hexdigest(),
}
(out / "verification.json").write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{roles['membership_checks']} routing membership checks, {len(pdf_markers)} PDF pages, "
      f"{sum(len(m['verified_terms']) for m in pdf_markers)} PDF facts, {len(set(local_links))} unique local links")
