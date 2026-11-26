"""Offline scorer input. Values under evidence fields are post-run annotations."""


def record(properties, required):
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


def choice(*values):
    return {"enum": list(values)}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def array(schema):
    return {"type": "array", "items": schema}


TEXT = {"type": "string", "pattern": r"\S"}
NUMBER = {"type": "string", "pattern": r"^-?[0-9]+(?:\.[0-9]+)?$", "maxLength": 80}
FLAG = {"type": "boolean"}
RUN = record({"id": TEXT, "valid": FLAG}, ["id", "valid"])
JUDGMENT = record({
    "stance": choice("explicit_accept", "conditions_resolved", "review", "exclude",
                     "refuting_alternative", "group_only", "alternative_only",
                     "conditions_open", "unresolved_conflict", "omitted"),
    "quote": nullable(TEXT), "source_ref": nullable(TEXT), "reason": TEXT,
}, ["stance", "quote", "source_ref", "reason"])
SCORE = record({
    "outcome": choice("detected", "missed", "false_alarm", "no_false_alarm", "unscorable"),
    "reason": TEXT,
}, ["outcome", "reason"])
ALTERNATIVE = {"oneOf": [
    record({"kind": {"const": "fixed"}, "basis": TEXT, "price": nullable(NUMBER)},
           ["kind", "basis", "price"]),
    record({"kind": {"const": "exclude_peer"}, "basis": TEXT, "peer_id": TEXT},
           ["kind", "basis", "peer_id"]),
]}
ITEM = record({
    "id": TEXT, "label": TEXT, "source_ref": TEXT, "candidate_id": nullable(TEXT),
    "subtype": nullable(TEXT), "mapping_reason": TEXT,
    "alternative": ALTERNATIVE, "a0": nullable(JUDGMENT), "b1": nullable(JUDGMENT),
    "b_proposal": choice("earnings", "aggregation"),
    "verified_fact_error_ref": nullable(TEXT), "qualitative_rule": nullable(TEXT),
    "resolved": FLAG, "blocking_info": FLAG,
}, ["id", "label", "source_ref", "candidate_id", "subtype", "mapping_reason",
    "alternative", "a0", "b1"])
TRIAL = record({
    "id": TEXT, "kind": choice("realistic", "control", "obvious"), "subtype": TEXT,
    "target_id": TEXT, "a0_run_id": TEXT, "a0": SCORE, "b1": SCORE, "b2": SCORE,
    "repeat_of": TEXT,
}, ["id", "kind", "subtype", "target_id", "a0_run_id", "a0", "b1"])
VALUATION = record({
    "eps_krw": nullable(NUMBER), "aggregation": choice("mean", "median", "other"),
    "peers": {"type": "object", "propertyNames": TEXT, "additionalProperties": nullable(NUMBER)},
    "basis": TEXT,
}, ["eps_krw", "aggregation", "peers", "basis"])
SCHEMA = record({
    "case_id": TEXT, "assignment_ref": TEXT, "k": {"type": "integer", "minimum": 0},
    "materiality_fraction": NUMBER, "qualitative_rules": {**array(TEXT), "uniqueItems": True},
    "disclosed_price_krw": nullable(NUMBER), "valuation": VALUATION,
    "a0_original": RUN, "b1": RUN, "b2": RUN, "items": {**array(ITEM), "minItems": 1},
    "trials": array(TRIAL),
}, ["case_id", "assignment_ref", "k", "materiality_fraction", "qualitative_rules",
    "disclosed_price_krw", "a0_original", "b1", "items", "trials"])


def example():
    """Synthetic only. No original filing, real responses or human grades are used."""
    def judgment(stance):
        return {"stance": stance, "quote": f"Synthetic explicit {stance}.",
                "source_ref": "synthetic source p.1", "reason": "Synthetic linked evidence."}

    def item(identifier, alternative, b_stance="explicit_accept", subtype=None):
        return {"id": identifier, "label": identifier, "source_ref": "synthetic filing p.1",
                "candidate_id": identifier if subtype else None,
                "subtype": subtype, "mapping_reason": "synthetic preassignment",
                "alternative": alternative, "a0": judgment("explicit_accept"),
                "b1": judgment(b_stance)}

    def score(outcome):
        return {"outcome": outcome, "reason": "Synthetic rubric annotation."}

    def trial(identifier, kind, a0, b1, b2):
        return {"id": identifier, "kind": kind, "subtype": "business-model",
                "target_id": f"target-{identifier}", "a0_run_id": f"A0-{identifier}",
                "a0": score(a0), "b1": score(b1), "b2": score(b2)}

    return {
        "case_id": "SYNTHETIC", "assignment_ref": "synthetic-v1", "k": 1,
        "materiality_fraction": "0.05", "qualitative_rules": [],
        "disclosed_price_krw": "3000",
        "valuation": {"eps_krw": "200", "aggregation": "median",
                      "peers": {"X": "18", "Y": "15", "Z": "12"}, "basis": "synthetic p.1"},
        "a0_original": {"id": "A0-original", "valid": True},
        "b1": {"id": "B1", "valid": True}, "b2": {"id": "B2", "valid": True},
        "items": [
            item("X", {"kind": "exclude_peer", "basis": "synthetic p.1", "peer_id": "X"},
                 "exclude", "business-model"),
            item("Y", {"kind": "exclude_peer", "basis": "synthetic p.1", "peer_id": "Y"},
                 subtype="business-model"),
            item("W", {"kind": "fixed", "basis": "synthetic period alternative", "price": "3240"}),
        ],
        "trials": [
            trial("T1", "realistic", "missed", "missed", "detected"),
            trial("T2", "realistic", "detected", "detected", "detected"),
            trial("C1", "control", "no_false_alarm", "no_false_alarm", "false_alarm"),
        ],
    }
