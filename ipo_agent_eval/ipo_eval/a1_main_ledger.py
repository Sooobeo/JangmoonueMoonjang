"""Durable, protocol-scoped Terra request reservations and exact wire evidence."""

import hashlib
import json
import sqlite3
import time
from contextlib import closing

# Monetary values use quarter-microdollars. Input costs five units/token at
# the conservative rate, and each output token costs twenty units.
GLOBAL_CAP = 60_000_000
LIMITS = {
    # per-request output, stage requests, cumulative output, cost, seconds
    "A0": (5100, 4, 12000, 5_000_000, 180),
    "C": (3500, 4, 12000, 5_000_000, 180),
    "A1_LOOK": (1100, 2, 2200, 2_500_000, 90),
    "A1_SELECT": (3800, 2, 9800, 2_500_000, 90),
}


class StageFailure(RuntimeError):
    """A recorded execution outcome prevents a compliant stage submission."""


class StopBatch(StageFailure):
    """Credit, enrollment or global accounting must be resolved first."""


class ConcurrentChange(RuntimeError):
    """Another worker won the same logical request reservation."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Ledger:
    def __init__(self, path, freeze_hash):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS freeze (id INTEGER PRIMARY KEY CHECK(id=1), hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempt (
                    id INTEGER PRIMARY KEY, receipt TEXT NOT NULL, stage TEXT NOT NULL, n INTEGER NOT NULL,
                    started REAL NOT NULL, input_n INTEGER NOT NULL, output_n INTEGER NOT NULL,
                    request BLOB NOT NULL, request_hash TEXT NOT NULL, kind TEXT NOT NULL,
                    UNIQUE(receipt,stage,n));
                CREATE TABLE IF NOT EXISTS outcome (
                    id INTEGER PRIMARY KEY REFERENCES attempt(id), elapsed REAL NOT NULL, status INTEGER,
                    body BLOB NOT NULL, body_hash TEXT NOT NULL, input_n INTEGER, output_n INTEGER,
                    error TEXT, blocked INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS billing_resume (through_id INTEGER PRIMARY KEY, recorded REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS response_headers (id INTEGER PRIMARY KEY REFERENCES outcome(id),
                                                            metadata TEXT NOT NULL);
                CREATE VIEW IF NOT EXISTS exposure AS
                    SELECT a.id,a.receipt,a.stage,
                    COALESCE(o.input_n,a.input_n) AS input_n, COALESCE(o.output_n,a.output_n) AS output_n
                    FROM attempt a LEFT JOIN outcome o USING(id);
            """)
            db.execute("INSERT OR IGNORE INTO freeze VALUES (1,?)", (freeze_hash,))
            if db.execute("SELECT hash FROM freeze").fetchone()[0] != freeze_hash:
                raise StopBatch("ledger_freeze_mismatch")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def history(self, receipt, stage):
        with closing(self.connect()) as db:
            return [
                dict(row)
                for row in db.execute(
                    """
                SELECT a.*,o.id AS finished,o.elapsed,o.status,o.body,o.body_hash,o.error,o.blocked,
                o.input_n AS actual_input,o.output_n AS actual_output,
                exists(SELECT 1 FROM billing_resume b WHERE b.through_id>=a.id) AS resumed
                FROM attempt a LEFT JOIN outcome o USING(id)
                WHERE receipt=? AND stage=? ORDER BY n""",
                    (receipt, stage),
                )
            ]

    @staticmethod
    def totals(db, receipt=None, stage=None):
        condition = " WHERE receipt=? AND stage=?" if receipt is not None else ""
        return db.execute(
            "SELECT COUNT(*),COALESCE(SUM(input_n),0),COALESCE(SUM(output_n),0) FROM exposure"
            + condition,
            (receipt, stage) if receipt is not None else (),
        ).fetchone()

    def verify_caps(self, receipt, stage):
        with closing(self.connect()) as db:
            self.check(db, receipt, stage, 0, 0, 0)

    def check(self, db, receipt, stage, increment, estimated, output):
        max_output, requests, stage_output, cap, _ = LIMITS[stage]
        n, i, o = self.totals(db)
        if (i + estimated) * 5 + (o + output) * 20 > GLOBAL_CAP or n + increment > 444:
            raise StopBatch("global_budget_or_request_cap")
        n, i, o = self.totals(db, receipt, stage)
        if (
            output > max_output
            or n + increment > requests
            or i + estimated > 800_000
            or o + output > stage_output
            or (i + estimated) * 5 + (o + output) * 20 > cap
        ):
            raise StageFailure("stage_budget_or_request_cap")

    def resume_billing(self):
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT OR IGNORE INTO billing_resume
                       SELECT MAX(id),? FROM outcome WHERE blocked=1 HAVING MAX(id) IS NOT NULL""",
                (time.time(),),
            )

    def reserve(self, receipt, stage, previous_count, wire, estimated, kind):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT COUNT(*) FROM outcome WHERE blocked=1
                      AND id>COALESCE((SELECT MAX(through_id) FROM billing_resume),0)""").fetchone()[
                0
            ]:
                raise StopBatch("billing_suspended")
            if self.totals(db, receipt, stage)[0] != previous_count:
                raise ConcurrentChange("issuer_stage_reserved_elsewhere")
            output = LIMITS[stage][0]
            self.check(db, receipt, stage, 1, estimated, output)
            return db.execute(
                """INSERT INTO attempt
                (receipt,stage,n,started,input_n,output_n,request,request_hash,kind)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    receipt,
                    stage,
                    previous_count + 1,
                    time.time(),
                    estimated,
                    output,
                    wire,
                    sha(wire),
                    kind,
                ),
            ).lastrowid

    def finish(
        self, identifier, elapsed, status, body, network_error=None, headers=None
    ):
        try:
            raw = json.loads(body)
        except (ValueError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        usage = raw.get("usage") or {}
        i, o = (
            usage.get(key) if isinstance(usage, dict) else None
            for key in ("input_tokens", "output_tokens")
        )
        if type(i) != int or type(o) != int or i < 0 or o < 0:
            i = o = None
        error = raw.get("error") or {}
        code = (
            (error.get("code") or error.get("type"))
            if isinstance(error, dict)
            else None
        )
        blocked = code in {
            "insufficient_quota",
            "credit_balance_exhausted",
            "billing_hard_limit_reached",
        }
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO outcome VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    elapsed,
                    status,
                    body,
                    sha(body),
                    i,
                    o,
                    network_error or code,
                    int(blocked),
                ),
            )
            if headers:
                db.execute(
                    "INSERT INTO response_headers VALUES(?,?)",
                    (identifier, json.dumps(headers)),
                )

    def summary(self):
        with closing(self.connect()) as db:
            n, i, o = self.totals(db)
            known, known_i, known_o = (
                db.execute("""SELECT COUNT(*), COALESCE(SUM(input_n),0),
                                   COALESCE(SUM(output_n),0) FROM outcome WHERE input_n IS NOT NULL""").fetchone()
            )
            return {
                "attempts": n,
                "known_usage": known,
                "unknown_or_pending": n - known,
                "known_standard_usd": (known_i + 5 * known_o) / 1e6,
                "accounted_ceiling_usd": (5 * i + 20 * o) / 4e6,
            }
