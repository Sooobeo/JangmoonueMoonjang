"""Cross-check the private registry against the original PDF/HTML using independent readers."""

import hashlib
import json
import re
import unicodedata

from lxml import html
from pypdf import PdfReader

from scripts.a1_main_foreign import BASE


def normalize(text):
    return "".join(unicodedata.normalize("NFKC", text).split()).replace("\xad", "")


def review():
    directory = BASE / "c_source"
    registry = json.loads((directory / "foreign.json").read_bytes())
    outcomes = []
    for receipt, peers in registry.items():
        for name, peer in peers.items():
            evidence = peer["business"] + peer["financials"]
            path = BASE / evidence[0]["snapshot"]
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            pdf = PdfReader(path) if path.suffix == ".pdf" else None
            if pdf is None:
                flat = "".join(
                    html.fromstring(
                        raw, parser=html.HTMLParser(encoding="utf-8")
                    ).itertext()
                )
            direct_ids = [name, peer["receipt"]]
            ticker = (
                r"(?<![a-zA-Z0-9])" + re.escape(peer["ticker"]) + r"(?![a-zA-Z0-9])"
            )
            matches = 0
            for row in evidence:
                if (
                    row["snapshot"] != path.relative_to(BASE).as_posix()
                    or row["sha256"] != digest
                ):
                    raise ValueError("Primary file digest/path mismatch: " + name)
                if pdf is not None:
                    page = int(re.search(r"page (\d+)", row["location"])[1])
                    flat = pdf.pages[page - 1].extract_text()
                if normalize(row["quote"]) not in normalize(flat):
                    raise ValueError(
                        "Original quotation mismatch: " + name + " " + row["location"]
                    )
                matches += 1
                excerpt = row["text"]
                if (
                    len(excerpt) > 350
                    or re.search(ticker, excerpt, re.IGNORECASE)
                    or re.search(r"https?://", excerpt, re.IGNORECASE)
                    or any(i.casefold() in excerpt.casefold() for i in direct_ids)
                ):
                    raise ValueError("Blind identifiers/length: " + name)
            for row in peer["financials"]:
                proof = row["period_proof"]
                header = flat
                if pdf is not None:
                    n = int(re.search(r"page (\d+)", proof["location"])[1])
                    header = pdf.pages[n - 1].extract_text()
                if not row["period"] or normalize(proof["quote"]) not in normalize(
                    header
                ):
                    raise ValueError("Financial period header mismatch: " + name)
            if peer["published"] >= receipt[:8] or not all(
                0 < len(peer[k]) <= 2 for k in ("business", "financials")
            ):
                raise ValueError("Source date or excerpt count: " + name)
            outcomes.append(
                {
                    "case": receipt,
                    "peer": name,
                    "ticker": peer["ticker"],
                    "quotes": len(evidence),
                    "matches": matches,
                    "dated_before_cutoff": True,
                    "lengths": [len(r["text"]) for r in evidence],
                    "sha_valid": True,
                    "has_business_and_financials": True,
                    "blind_identifiers_absent": True,
                    "checked_financial_periods": [
                        r["period"] for r in peer["financials"]
                    ],
                }
            )
    path = directory / "foreign_crosscheck.json"
    path.write_text(
        json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(
        len(outcomes),
        "peers,",
        sum(r["matches"] for r in outcomes),
        "exact normalized source quotations",
    )


if __name__ == "__main__":
    review()
