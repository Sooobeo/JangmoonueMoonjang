"""Read only the explicitly named public corpus; never recurse into a workspace."""
import hashlib
import json
import math
import re
from pathlib import Path


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def normalized(text):
    return re.sub(r"\s+", "", text).casefold()


class Corpus:
    def __init__(self, directory, case_id):
        self.directory = Path(directory).resolve()
        manifests = read_jsonl(self.directory / "case_manifest.jsonl")
        self.case = next(item for item in manifests if item["case_id"] == case_id)
        allowed = set(self.case["allowed_doc_ids"])
        self.documents = [d for d in read_jsonl(self.directory / "documents.jsonl") if d["doc_id"] in allowed]
        if set(d["doc_id"] for d in self.documents) != allowed:
            raise ValueError("Missing allowed document metadata")
        self.chunks = [c for c in read_jsonl(self.directory / "chunks.jsonl")
                       if c["case_id"] == case_id and c["doc_id"] in allowed and c["cutoff_status"] == "BEFORE"]
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        if len(self.by_id) != len(self.chunks):
            raise ValueError("Duplicate chunk IDs")
        self.manual = (self.directory / "manual.md").read_text(encoding="utf-8-sig")
        self.texts = {c["chunk_id"]: normalized(c["text"]) for c in self.chunks}

    def verify(self):
        checks = []
        for doc in self.documents:
            raw = self.directory / "raw" / (doc["doc_id"] + ".pdf")
            actual = hashlib.sha256(raw.read_bytes()).hexdigest()
            if actual != doc["sha256"]:
                raise ValueError("Source PDF hash mismatch: " + doc["doc_id"])
            if doc["cutoff_status"] != "BEFORE":
                raise ValueError("Document cutoff has not been verified")
            pages = sorted(c["page"] for c in self.chunks if c["doc_id"] == doc["doc_id"])
            if pages != list(range(1, doc["pages"] + 1)):
                raise ValueError("Missing or duplicate source pages")
            checks.append({"doc_id": doc["doc_id"], "sha256": actual, "pages": len(pages), "cutoff_status": "BEFORE"})
        return checks

    def public_metadata(self):
        # Audit snapshots may contain later DART links: they never enter a prompt.
        doc_keys = ("doc_id", "title", "source_url", "sha256", "pages", "available_at", "cutoff_status", "version_note")
        return {"case": {k: self.case[k] for k in ("case_id", "issuer_name", "cutoff_at", "allowed_doc_ids")},
                "documents": [{k: d.get(k) for k in doc_keys} for d in self.documents]}

    def search_corpus(self, case_id, query, filters=None, top_k=3):
        if case_id != self.case["case_id"]:
            raise ValueError("Case is not allowed")
        filters = filters or {}
        if set(filters) - {"doc_id", "cutoff_status"}:
            raise ValueError("Unsupported search filters")
        terms = [normalized(t) for t in query.split()]
        count = len(self.chunks)
        weights = {t: math.log(1 + count / (1 + sum(t in s for s in self.texts.values()))) for t in terms}
        ranked = []
        for chunk in self.chunks:
            if any(chunk.get(k) != v for k, v in filters.items()):
                continue
            content = self.texts[chunk["chunk_id"]]
            score = sum(weights[t] * (1 + min(content.count(t), 4) * 0.15) for t in terms if t in content)
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1]["doc_id"], item[1]["page"]))
        hits = []
        for score, chunk in ranked[:top_k]:
            # Excerpts are explicitly partial; read_source returns the full page.
            hits.append({"doc_id": chunk["doc_id"], "chunk_id": chunk["chunk_id"], "page": chunk["page"],
                         "score": round(score, 6), "excerpt": chunk["text"][:300],
                         "excerpt_truncated": len(chunk["text"]) > 300})
        return {"query": query, "hits": hits, "total_matches": len(ranked)}

    def read_source(self, chunk_ids, neighbor_pages=0):
        wanted = set()
        for chunk_id in chunk_ids:
            if chunk_id not in self.by_id:
                raise ValueError("Unknown or disallowed chunk: " + chunk_id)
            chunk = self.by_id[chunk_id]
            for candidate in self.chunks:
                if candidate["doc_id"] == chunk["doc_id"] and abs(candidate["page"] - chunk["page"]) <= neighbor_pages:
                    wanted.add(candidate["chunk_id"])
        selected = sorted((self.by_id[i] for i in wanted), key=lambda c: (c["doc_id"], c["page"]))
        keys = ("case_id", "doc_id", "chunk_id", "page", "printed_page", "text", "source_url", "available_at", "cutoff_status", "section_state")
        return {"chunks": [{k: c.get(k) for k in keys} for c in selected], "truncated": False,
                "page_convention": "page is the physical PDF page, starting at 1; printed_page is the footer when confirmed"}
