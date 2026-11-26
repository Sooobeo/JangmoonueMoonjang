"""Rebuild the two source inventories and the name-only crosswalk locally."""

import csv
import gzip
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import fitz
from lxml import html

HERE = Path(__file__).resolve().parent


def write(name, rows):
    with (HERE / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def holdings():
    archived = HERE / "edgar-mirror.htm.gz"
    raw = gzip.decompress(archived.read_bytes()) if archived.exists() else (HERE / "edgar-mirror.htm").read_bytes()
    assert len(raw) == 42245733
    assert hashlib.sha256(raw).hexdigest() == "a15da728f3a02be5cdba3e9ad5dbd7a37ddad9cd98f1c0fac3743a6b797327cf"
    tables = html.fromstring(raw).xpath("//table")
    rows, country_sums, country_printed = [], Counter(), {}
    country, ended = None, False
    for ti in range(198, 434):
        for ri, tr in enumerate(tables[ti].xpath("./tr|./tbody/tr")):
            cells = [" ".join(c.text_content().split()) for c in tr.xpath("./th|./td")]
            text = " ".join(cells).strip()
            if text.startswith("Total Common Stocks"):
                assert cells[-1] == "36,356,741"
                ended = True
                break
            if not text or "Market Value" in text or text == "Common Stocks (98.8%)":
                continue
            if len(cells) == 1 and re.fullmatch(r".+ \([-0-9.]+%\)", text):
                country = text.rsplit(" (", 1)[0]
            elif len(cells) == 4 and cells[1]:
                assert country and all(re.fullmatch(r"[\d,]+|—", v) for v in cells[2:])
                rows.append({"country": country, "holding": cells[1], "shares": cells[2],
                             "market_value_usd_thousands": cells[3], "footnotes": cells[0], "table_0b": ti, "tr_0b": ri})
                country_sums[country] += int(cells[3].replace(",", "").replace("—", "0"))
            else:
                assert re.fullmatch(r"[\d,]+|—", text)
                country_printed[country] = int(text.replace(",", "").replace("—", "0"))
    assert ended and len(country_sums) == 50 and len(rows) == 9617
    assert dict(country_sums) == country_printed and sum(country_sums.values()) == 36356741
    write("total_world_common_stock_holdings.csv", rows)
    return rows


def directory():
    """Include all blue bold entry headings on physical pages 38–65; join wrapped headings."""
    rows = []
    with fitz.open(HERE / "smi_directory_2024.pdf") as pdf:
        for index in range(37, 65):
            prev = None
            for block in pdf[index].get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        t = s["text"].strip()
                        if s["font"] != "Montserrat-Bold" or abs(s["size"] - 7.6) >= .15 or s["color"] != 41370:
                            continue
                        if not t or ":" in t:
                            prev = None
                            continue
                        x, y = s["bbox"][:2]
                        if prev and abs(x - prev[0]) < 2 and 0 < y - prev[1] < 12:
                            rows[-1]["directory_name"] += " " + t
                        else:
                            rows.append({"pdf_page_1b": index + 1, "x_pt": round(x), "y_pt": round(y),
                                         "directory_name": t})
                        prev = x, y
    assert {row["pdf_page_1b"] for row in rows} == set(range(38, 66))
    return rows


def normalize(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", ascii_name)
    aliases = {"limited": "ltd", "corporation": "corp", "incorporated": "inc", "company": "co"}
    return tuple(aliases.get(w, w) for w in words)


def compare(members, stocks):
    ending = {"ltd", "corp", "inc", "co", "plc", "oyj", "abp", "ag", "ab", "nv", "sa",
              "class", "a", "b", "holdings", "group", "spa", "se", "asa", "as", "registered"}
    by_initial = defaultdict(list)
    with (HERE / "listed_identity_checks.csv").open(encoding="utf-8") as handle:
        identity_checks = {row["directory_name"]: row for row in csv.DictReader(handle)}
    for r in stocks:
        words = normalize(r["holding"])
        if words:
            by_initial[words[0]].append((words, r))
    for m in members:
        key = normalize(m["directory_name"])
        options = []
        for other, stock in by_initial[key[0]]:
            n = 0
            for x, y in zip(key, other, strict=False):
                if x != y:
                    break
                n += 1
            if key == other:
                level = 3
            elif tuple(w for w in key if w not in ending) == tuple(w for w in other if w not in ending):
                level = 2
            elif n >= 2 or (len(key[0]) >= 4 and key[0] not in {"the", "first", "group", "marine", "royal", "university", "national"}):
                level = 1
            else:
                continue
            options.append((level, n, stock))
        # Names and legal suffixes generate pointers, never parent/subsidiary rulings.
        best = max(((level, n) for level, n, _ in options), default=(0, 0))
        chosen = [s for level, n, s in options if (level, n) == best]
        m.update(match_level=["no_lexical_hit", "prefix_only", "core_name", "full_name"][best[0]],
                 matched_positions=len(chosen), holding_names=" | ".join(s["holding"] for s in chosen),
                 holding_rows=" | ".join(f"{s['table_0b']}:{s['tr_0b']}" for s in chosen),
                 issuer_identity="unverified", business_and_financial_eligibility="unverified")
        if m["directory_name"] in identity_checks:
            check = identity_checks[m["directory_name"]]
            assert m["match_level"] == "core_name" and m["holding_names"] == check["holding_name"]
            assert (HERE / check["local_source"]).is_file()
            m["issuer_identity"] = check["status"]
    explicit_uk = {m["directory_name"] for m in members if m["match_level"] == "core_name"
                   and normalize(m["directory_name"])[-1] in {"plc", "ltd"}}
    assert explicit_uk == set(identity_checks)
    write("smi_vanguard_name_crosswalk.csv", members)
    return dict(Counter(m["match_level"] for m in members))


if __name__ == "__main__":
    stocks = holdings()
    members = directory()
    print(len(stocks), len(members), compare(members, stocks))
