"""Preparation rejects unverified/changed inputs and never rewrites old corpora."""
import importlib.util
import json
from pathlib import Path

import fitz
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_case.py"
_spec = importlib.util.spec_from_file_location("prepare_case", SCRIPT)
prepare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepare)


@pytest.fixture(params=["Page 7", "- 7 -"])
def source(tmp_path, request):
    public = tmp_path / "data/cases/MELCON-DEV-01/public"
    (public / "raw").mkdir(parents=True)
    (public / "provenance").mkdir()
    methods = tmp_path / "data/methods"
    methods.mkdir()
    (methods / "IPO_PER_B_v0.2.md").write_text("Generic method only", encoding="utf-8")
    pdf_path = public / "raw/MELCON-PROS-01.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 40), "Test public full page")
        page.insert_text((40, 800), request.param)
        pdf.save(pdf_path)
    spec = {"case_id": "MELCON-DEV-01", "doc_id": "MELCON-PROS-01", "issuer_name": "Synthetic",
            "issuer_legal_name": "Synthetic Ltd", "market": "TEST", "receipt_no": "20000102000001",
            "original_receipt_no": "20000101000001", "dart_url": "https://example.invalid/receipt",
            "source_url": "https://example.invalid/source.pdf", "version_date": "2000-01-02",
            "cutoff_at": "2000-01-02T23:59:59+09:00", "general_subscription_start": "2000-01-03",
            "expected_sha256": prepare.digest(pdf_path.read_bytes()), "expected_pages": 1,
            "version_note": "Synthetic historical metadata", "version_checks": {"receipt": True},
            "version_evidence": [{"locator": "Synthetic title"}]}
    (public / "provenance/source_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    legacy = tmp_path / "data/public"
    legacy.mkdir()
    (legacy / "legacy_input.txt").write_bytes(b"PRESERVE_LEGACY_INPUT")
    return tmp_path, public, spec


def test_full_pdf_footer_identity_and_idempotence(source):
    root, public, _ = source
    first = prepare.build("MELCON-DEV-01", root)
    chunks = [json.loads(line) for line in (public / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert chunks[0]["page"] == 1 and chunks[0]["printed_page"] == 7
    assert "Test public full page" in chunks[0]["text"]
    assert chunks[0]["text_sha256"] == prepare.digest(chunks[0]["text"].encode())
    original = {p.name: p.read_bytes() for p in public.glob("*.jsonl")}
    assert prepare.build("MELCON-DEV-01", root) == first
    assert original == {p.name: p.read_bytes() for p in public.glob("*.jsonl")}
    assert (root / "data/public/legacy_input.txt").read_bytes() == b"PRESERVE_LEGACY_INPUT"


@pytest.mark.parametrize("case_id", ["HDMS-DEV-01", "../../private", "UNKNOWN"])
def test_unregistered_or_legacy_destination_rejected(source, case_id):
    root, public, _ = source
    with pytest.raises(ValueError):
        prepare.build(case_id, root)
    assert not (public / "chunks.jsonl").exists()


def test_changed_provenance_cannot_silently_leave_stale_summary(source):
    root, public, spec = source
    prepare.build("MELCON-DEV-01", root)
    saved = (public / "provenance/preparation_summary.json").read_bytes()
    spec["additional_audit_note"] = "Changed source evidence"
    (public / "provenance/source_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(FileExistsError, match="saved summary"):
        prepare.build("MELCON-DEV-01", root)
    assert (public / "provenance/preparation_summary.json").read_bytes() == saved


@pytest.mark.parametrize("change", [
    {"version_checks": {"receipt": False}},
    {"version_checks": {"receipt": "true"}},
    {"version_date": "2000-01-04"},
    {"receipt_no": "19991231000001"},
    {"expected_sha256": "0" * 64},
    {"expected_pages": 2},
    {"cutoff_at": "2000-01-02T23:59:59"},
])
def test_unverified_source_cannot_be_prepared(source, change):
    root, public, spec = source
    spec.update(change)
    (public / "provenance/source_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError):
        prepare.build("MELCON-DEV-01", root)
    assert not (public / "chunks.jsonl").exists()


def test_different_existing_outputs_are_preserved_before_any_write(source):
    root, public, _ = source
    (public / "documents.jsonl").write_bytes(b"DO NOT OVERWRITE")
    with pytest.raises(FileExistsError):
        prepare.build("MELCON-DEV-01", root)
    assert (public / "documents.jsonl").read_bytes() == b"DO NOT OVERWRITE"
    assert not (public / "case_manifest.jsonl").exists()
    assert not (public / "chunks.jsonl").exists()
