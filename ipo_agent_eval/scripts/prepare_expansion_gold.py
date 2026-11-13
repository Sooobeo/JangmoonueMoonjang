"""Prepare private pre-response rubrics for the three W09 development cases.

All amounts are transcribed from the archived primary prospectus. Decimal
recalculation separates displayed inputs from disclosed full-precision outputs.
This script never reads a model answer and never writes public model inputs.
"""
from __future__ import annotations

from decimal import Decimal, getcontext
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
getcontext().prec = 40
D = Decimal


def evidence(doc, page, locator):
    return {"doc_id": doc, "chunk_id": f"{doc}-p{page:04d}", "page": page,
            "printed_page": page - 2, "locator": locator}


def entry(required, evidence_rows, **values):
    return {"required": required, **values, "evidence": evidence_rows}


def prepare(case, doc, spec):
    base = ROOT / "data/cases" / case
    private = base / "private"
    source = json.loads((base / "public/provenance/source_spec.json").read_bytes())
    chunks = {r["chunk_id"]: r for r in map(json.loads, (base / "public/chunks.jsonl").read_text(encoding="utf8").splitlines())}
    gold = {"case_id": case, "version": "1.0", "prepared_on": "2026-11-13",
            "locked_before_model_answer": True, "private_do_not_include_in_model_input": True,
            "cohort": "DEVELOPMENT_PILOT", "grading_status": "RUBRIC_PREPARED_NO_MODEL_RESPONSE_REVIEWED",
            "human_review_status": "NOT_YET_REVIEWED", "assistance": "Codex AI prepared from primary sources",
            "source_sha256": source["expected_sha256"],
            "scoring": {"facts": {"items": 5, "range_each": [0, 1]},
                        "calculations": {"items": 3, "range_each": [0, 1]},
                        "judgment": {"items": 4, "range_each": [0, 1, 2]},
                        "main_method_metric": "count(J_i == 2) / 4; do not substitute sum(J_i)/8",
                        "independent_alternatives": "Evidence-supported acceptance, conditional acceptance, rejection or a specific information request can receive full credit; do not force an invented error or every optional discrepancy."},
            **spec}
    earnings = D(gold["inputs"]["earnings_krw"])
    per = D(gold["inputs"]["applied_per"])
    shares = sum(D(v) for v in gold["inputs"]["share_components"].values())
    disclosed_shares = D(gold["inputs"]["shares"])
    assert shares == disclosed_shares
    base_price = earnings * per / shares
    calc = {"share_component_sum": str(shares), "earnings_krw": str(earnings),
            "eps_krw": str(earnings / shares), "displayed_inputs_equity_krw": str(earnings * per),
            "displayed_inputs_price_krw": str(base_price),
            "difference_from_disclosed_price_krw": str(base_price - D(gold["inputs"]["valuation_price"])),
            "displayed_peer_mean": str(sum(D(p["per"]) for p in gold["inputs"]["peers"]) / D(len(gold["inputs"]["peers"]))) }
    if "equity_krw" in gold["inputs"]:
        calc["disclosed_equity_based_price_krw"] = str(D(gold["inputs"]["equity_krw"]) / shares)
        calc["displayed_equity_minus_disclosed_krw"] = str(earnings * per - D(gold["inputs"]["equity_krw"]))
    calc["peer_per_from_source_cap_and_earnings"] = {p["name"]: str(D(p["cap"])/D(p["earnings"])) for p in gold["inputs"]["peers"]}
    gold["computed"] = calc
    gold["sensitivity_scenarios"] = []
    peer_values = sorted(D(p["per"]) for p in gold["inputs"]["peers"])
    median = (peer_values[(len(peer_values)-1)//2] + peer_values[len(peer_values)//2])/2
    scenarios = [("Displayed peer median (interpretation required)", median)]
    scenarios += [(p["name"] + " only (not automatic exclusion of other peers)", D(p["per"])) for p in gold["inputs"]["peers"]]
    for name, alt_per in scenarios:
        price = earnings * alt_per / shares
        gold["sensitivity_scenarios"].append({"name": name, "per": str(alt_per), "earnings_krw": str(earnings),
                                               "shares": str(shares), "price_krw": str(price),
                                               "change_from_displayed_input_base_pct": str((price/base_price-1)*100)})
    gold["optional_findings_policy"] = "F checks reported operative values; K checks arithmetic with units and precision. Do not silently replace the reported denominator or rounded inputs. Accept equally well-sourced alternatives and do not require every optional anomaly for J=2."
    gold["not_independently_verified"] = ["Peer original filings outside this prospectus", "KRX daily prices outside this prospectus", "Full-precision valuation workbook and issuer-specific accounting normalization"]
    references = []
    def validate(value):
        if isinstance(value, dict):
            if "chunk_id" in value:
                chunk = chunks[value["chunk_id"]]
                assert chunk["page"] == value["page"] and chunk["printed_page"] == value["printed_page"]
                references.append(value["chunk_id"])
            for v in value.values():
                validate(v)
        elif isinstance(value, list):
            for v in value:
                validate(v)
    validate(gold)
    private.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(gold, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    path = private / "gold.json"
    if path.exists() and path.read_bytes() != raw:
        raise FileExistsError(f"Refuse to alter locked rubric: {path}")
    if not path.exists():
        path.write_bytes(raw)
    return {"case_id": case, "gold_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "gold_sha256": hashlib.sha256(raw).hexdigest(), "evidence_references_checked": len(references),
            "unique_evidence_pages": sorted({chunks[c]["page"] for c in references}),
            "share_sum_pass": True, "computed": calc, "human_review_status": "NOT_YET_REVIEWED"}


def build_specs():
    specs = []
    case, doc = "SHINSUNGST-DEV-01", "SHINSUNGST-PROS-01"
    e = lambda p, l: evidence(doc, p, l)
    valuation = [e(245, "신성에스티 PER 평가가치 및 주1~3")]
    peers = [e(244, "2023 반기 연환산 유사기업 PER"), e(245, "지배순이익 및 기준일 주석")]
    specs.append((case, doc, {
        "inputs": {"earnings_krw": "14669632980", "applied_per": "21.8", "shares": "9046771", "valuation_price": "35360", "offer_price": "26000",
                   "share_components": {"existing": "7001316", "public_new": "2000000", "underwriter_at_lower_band": "45455"},
                   "peers": [{"name": n, "per": p, "cap": c, "earnings": t, "amount_unit": "KRW"} for n,p,c,t in [
                       ("신흥에스이씨", "12.8", "372790256580", "29221388560"), ("상신이디피", "11.4", "244326710232", "21421290130"),
                       ("삼기이브이", "45.1", "198613943400", "4406895786"), ("영화테크", "17.7", "109444203678", "6174441852")]]},
        "facts": {
            "F1": entry("2023H1 actual profit 7,334,816,490 KRW multiplied by 2 gives applied 14,669,632,980 KRW; historical annualization, not an independently forecast full year.", valuation),
            "F2": entry("Four named peers 12.8/11.4/45.1/17.7, arithmetic mean applied 21.8; peers also H1 controlling profit annualized. Price basis 2023-08-11, lower of one-month and one-week average closes.", peers),
            "F3": entry("Reported EPS 1,622 KRW and applied shares 9,046,771; distinguish rounded EPS from the full earnings/share ratio.", valuation),
            "F4": entry("7,001,316 existing + 2,000,000 new issue + 45,455 mandatory underwriter = 9,046,771. Underwriter count explicitly based on lower offer band; preserve this valuation basis before any proposed update.", valuation),
            "F5": entry("Reported valuation 35,360 KRW versus final offer 26,000 KRW.", valuation)},
        "calculations": {
            "K1": {"pass": "Correct labelled share sum 7,001,316+2,000,000+45,455=9,046,771; any revised share basis must be sourced and reconciled to the disclosed base.", "evidence": valuation},
            "K2": {"pass": "14,669,632,980 / 9,046,771 produces full-precision EPS, compared with reported 1,622 KRW; do not confuse KRW and million KRW.", "evidence": valuation},
            "K3": {"pass": "Compute earnings/shares*21.8 and separately 1,622*21.8; quantify difference from 35,360 and identify displayed precision as a possible, unverified explanation. Do not force an arithmetic-error finding.", "evidence": peers + valuation}},
        "judgments": {
            "J1": {"two": "Use H1 annualization for issuer and peers, controlling basis for consolidated peers, then explain seasonality/earnings persistence or accounting comparability and a resulting acceptance condition or substantiated acceptance.", "one": "Correct basis with a generic caution but no implication.", "zero": "Wrong period/basis or no earnings review.", "evidence": valuation + peers},
            "J2": {"two": "Connect at least one named peer's concrete product commonality and difference to PER transferability: issuer Busbar/module cases vs cap assembly/CAN/endplate/electrical parts. Shared battery demand alone is insufficient; explain product economics or peer dispersion with evidence.", "one": "Concrete similarity or difference without valuation implication.", "zero": "Only same industry or underwriter selected them.", "evidence": [e(240, "Busbar/module case and comparison product mix"), e(241, "battery part peer businesses")]},
            "J3": {"two": "Recompute a sourced alternative (e.g. median PER15.25 or justified peer subset), explain rationale, comparable baseline, direction and size. PER45.1 alone does not automatically warrant exclusion; distinguish sensitivity from a proved error.", "one": "Correct number but no justified rationale or magnitude.", "zero": "No alternative, wrong calculation or invented fact.", "evidence": peers + valuation + [e(237, "PER50 exclusion criterion")]},
            "J4": {"two": "Distinguish replication within the prospectus from independent peer/price verification; identify a concrete unresolved assumption and source/action, such as full precision, updated mandatory-acquisition basis or sustained H1 earnings; connect request to a decision.", "one": "Generic additional-data request.", "zero": "Unsupported all-verified claim or no verification limit/next step.", "evidence": valuation + peers}},
        "source_discrepancies": [{"issue": "Valuation uses a lower-band mandatory acquisition count despite final offer above band; preserve the disclosed denominator and request/reconcile a current basis if used. No updated count has been independently certified here.", "evidence": valuation}]
    }))
    case, doc = "ALT-DEV-01", "ALT-PROS-01"
    e = lambda p, l: evidence(doc, p, l)
    valuation = [e(251, "에이엘티 평가표, 과세 조정 주1"), e(252, "기간 실적 및 희석주식수")]
    specs.append((case, doc, {
        "inputs": {"earnings_krw": "13508336854", "applied_per": "18.0", "equity_krw": "243231794648", "shares": "8960259", "valuation_price": "27146", "offer_price": "25000",
                   "share_components": {"existing": "7562671", "public_new": "900000", "underwriter": "27000", "convertible_bond_dilution": "470588"},
                   "peers": [{"name": n, "per": p, "cap": c, "earnings": t, "amount_unit": "million KRW"} for n,p,c,t in [
                       ("LB세미콘", "13.8", "325407", "23634"), ("LB루셈", "25.8", "178547", "6931"),
                       ("두산테스나", "11.1", "523817", "47283"), ("네패스아크", "21.4", "263175", "12280")]]},
        "facts": {
            "F1": entry("2022Apr-Dec pretax 9,916,809,866 +2023Q1 controlling net 3,591,526,988 =13,508,336,854 KRW; adjustment removes 2022 tax benefit4,133,157,502, retains Q1 tax expense427,270,312.", valuation),
            "F2": entry("LB세미콘13.8, LB루셈25.8, 두산테스나11.1, 네패스아크21.4, applied18.0. Peer historical TTM to2023Q1; 2023-05-18 min daily/weekly/monthly price basis.", [e(251, "유사기업 PER 표와 주1~2")]),
            "F3": entry("Reported equity243,231,794,648 KRW and diluted shares8,960,259.", valuation),
            "F4": entry("7,562,671 existing +900,000 new +27,000 mandatory +470,588 convertible dilution=8,960,259; convertible bonds are not options.", [e(252, "공모 후 주주구성")]),
            "F5": entry("Reported value27,146 KRW versus final offer25,000 KRW.", [e(252, "희망공모가액 산출내역")])},
        "calculations": {
            "K1": {"pass": "Correct labelled sum of four share components to8,960,259.", "evidence": [e(252, "희석주식수 구성")]},
            "K2": {"pass": "Reported equity243,231,794,648 /8,960,259, compared with reported27,146; units explicit.", "evidence": valuation},
            "K3": {"pass": "13,508,336,854*18.0 /8,960,259; quantify discrepancy from reported equity/price and acknowledge hidden PER precision may explain it but has not been independently verified.", "evidence": valuation}},
        "judgments": {
            "J1": {"two": "Recognize mixed pretax2022/aftertax2023Q1 basis and stated noncash tax-benefit adjustment; assess whether normalized aftertax/controlling earnings and peer TTM are comparable, connecting to a reasoned acceptance/condition rather than treating tax adjustment as necessarily wrong.", "one": "Names adjustment but no comparability implication.", "zero": "Treats the input as unadjusted annual or forecast profit, or no review.", "evidence": valuation},
            "J2": {"two": "Use issuer wafer test84.43% (Q1) and at least one named peer's concrete mix (Doosan wafer92.54%, Nepes95.49%, LB Lusem COF89.63%) to assess OSAT commonality and testing/packaging differences, connecting to PER comparability.", "one": "Concrete mix detail without valuation implication.", "zero": "Only same industry or copied selection without analysis.", "evidence": [e(243, "issuer product mix"), e(246, "peer business mix")]},
            "J3": {"two": "Provide a transparent sourced alternative such as PER median17.6 or justified test-focused peer set, or an explicitly sourced earnings-normalization sensitivity, with same share/unit basis, rationale and magnitude. Any hypothetical tax rate must be labelled as a scenario.", "one": "Numeric alternative without rationale/baseline/interpretation.", "zero": "Missing/wrong calculation or invented actual normalized tax.", "evidence": valuation},
            "J4": {"two": "Separate prospectus replication from independent verification; request specific tax/controlling-interest reconciliation, full precision or source peer filings/prices and explain what decision depends on it. Already disclosed tax table is not absent.", "one": "Only generic limitation/request.", "zero": "Unfounded verification or unavailable-source assertion.", "evidence": valuation}},
        "source_discrepancies": [{"issue": "Rounded applied PER18.0 does not exactly reproduce disclosed equity. A precision gap is not sufficient proof of substantive valuation error.", "evidence": valuation}]
    }))
    case, doc = "MILLIE-DEV-01", "MILLIE-PROS-01"
    e = lambda p, l: evidence(doc, p, l)
    valuation = [e(293, "밀리의서재 평가표 및 주1~3")]
    peers = [e(292, "peer H1 earnings and method limits"), e(293, "annualization, PER and price basis")]
    specs.append((case, doc, {
        "inputs": {"earnings_krw": "10255482000", "applied_per": "30.55", "equity_krw": "313270316000", "shares": "8422810", "valuation_price": "37193", "offer_price": "23000",
                   "share_components": {"existing": "6566910", "public_new": "1500000", "underwriter": "45000", "immediately_exercisable_options": "310900"},
                   "peers": [{"name": n, "per": p, "cap": c, "earnings": t, "amount_unit": "thousand KRW"} for n,p,c,t in [
                       ("미스터블루", "17.74", "159447001", "8989274"), ("예스24", "43.36", "118460938", "2732299")]]},
        "facts": {
            "F1": entry("Actual2023H1 5,127,741 thousand KRW*2=10,255,482 thousand KRW (10,255,482,000 KRW). Historical annualization, not independent earnings forecast.", valuation),
            "F2": entry("미스터블루17.74/예스24 43.36, average30.55, H1 controlling earnings annualized; min20day/5day/asof close on2023-08-11.", peers),
            "F3": entry("Reported equity313,270,316 thousand KRW and shares8,422,810; explicitly retain thousand vs KRW conversion.", valuation),
            "F4": entry("6,566,910 existing+1,500,000 new+45,000 mandatory+310,900 immediately exercisable options=8,422,810.", valuation),
            "F5": entry("Reported valuation37,193 KRW versus final offer23,000 KRW.", [e(294, "확정공모가액 산출내역")])},
        "calculations": {
            "K1": {"pass": "Correct labelled share component sum8,422,810; distinguish options from mandatory underwriting.", "evidence": valuation},
            "K2": {"pass": "313,270,316 thousand*1000 /8,422,810, compared with reported37,193 KRW.", "evidence": valuation},
            "K3": {"pass": "10,255,482 thousand*1000*30.55 /8,422,810; quantify difference from reported value and distinguish displayed precision from an independently verified formula.", "evidence": peers+valuation}},
        "judgments": {
            "J1": {"two": "Identify matching H1 annualization/controlling basis then explain earnings sustainability/seasonality or business mix and the implication for a reasoned acceptance condition. The disclosed historical annualization is not the same as a multi-year profit forecast.", "one": "Basis correct but only generic caution.", "zero": "Wrong earnings period/basis or no review.", "evidence": peers+valuation},
            "J2": {"two": "Use issuer unlimited ebook/audio subscription vs a named peer: MrBlue webtoon/webnovel content/IP/platform charging, or YES24 online book retail plus ebooks/ticketing. Explain shared digital content and a concrete revenue/customer/IP difference affecting multiple transfer.", "one": "Concrete commonality/difference but no valuation consequence.", "zero": "Only same industry or unsupported peer identity.", "evidence": [e(285, "issuer subscription business"), e(288, "MrBlue/YES24 businesses")]},
            "J3": {"two": "Recalculate a justified single-peer, earnings or other sourced scenario with baseline/magnitude. With two peers the median equals the mean30.55; merely renaming mean as median is insufficient substantive sensitivity.", "one": "Correct alternate number without rationale/baseline/interpretation.", "zero": "No meaningful alternative, wrong formula or invented fact.", "evidence": peers+valuation},
            "J4": {"two": "Distinguish internal source replication and independent price/peer filing checks; specify unresolved earnings sustainability, mix, tax/controlling basis or full precision and a source/action with decision implication. Do not claim inaccessible sources are unavailable without checking.", "one": "Generic additional information only.", "zero": "Unsubstantiated all-verified conclusion or no next step.", "evidence": peers+valuation}},
        "source_discrepancies": [{"issue": "YES24 displayed H1 1,366,150 thousand doubled is2,732,300, while annualized table2,732,299; preserve original values and note displayed precision uncertainty. Not mandatory to reject the valuation on a one-thousand-KRW display gap.", "evidence": peers}]
    }))
    return specs


if __name__ == "__main__":
    reports = [prepare(*spec) for spec in build_specs()]
    path = ROOT / "reports/a0_implementation/case_roster_gold_checks.json"
    data = {"review_date": "2026-11-13", "status": "PASS_AUTOMATED_SOURCE_LINKS_AND_DECIMAL_CHECKS", "cases": reports,
            "limits": "AI-prepared criteria, no human scoring adjudication; no model response used; check findings do not prove full accounting/source independence."}
    raw = (json.dumps(data, ensure_ascii=False, indent=2)+"\n").encode("utf8")
    if path.exists() and path.read_bytes() != raw:
        raise FileExistsError(path)
    if not path.exists():
        path.write_bytes(raw)
    print(json.dumps(data, ensure_ascii=False, indent=2))
