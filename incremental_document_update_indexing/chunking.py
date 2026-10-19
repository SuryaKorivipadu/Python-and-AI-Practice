"""Text normalization and chunk-identity hashing.

The core trick that makes incremental reindexing possible: a chunk's ID is derived from (document, position, normalized content) rather than assigned sequentially or derived from the whole document. That means editing one paragraph in a 50-paragraph document changes exactly one chunk_id -- every other paragraph's identity is untouched, so the diff against the stored manifest naturally isolates the change instead of invalidating the document.

Position is part of the identity (not just content) so that two unrelated paragraphs that happen to contain identical text don't collide, and so that inserting a new paragraph is seen as one add rather than shifting every downstream chunk's identity by one slot.
"""

import hashlib, re, uuid

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse whitespace and case so trivial formatting chunk (double spaces, trailing newlines, tab vs. space) doesn't register as a content change."""
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def content_hash(text: str) -> str:
    """Hash of normalized content alone (position-independent). Used to detect a chunk that moved position but is otherwise byte-for-byte identical, so it can be treated as a cheap reactivation rather than an add + delete pair."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def chunk_id(doc_id: str, position: int, text: str) -> str:
    """Stable identity for a chunk: doc + position + normalized content.

    doc_id is included (in addition to the spec's "normalized text + position") because position numbers are only unique within a document -- without doc_id, chunk 0 of two different documents with the same first paragraph would collide and one would silently shadow the other.
    """
    normalized = normalize_text(text)
    digest = hashlib.sha256(f"{doc_id}\x1f{position}\x1f{normalized}".encode("utf-8"))
    return digest.hexdigest()


class Chunk:
    def __init__(self, doc_id: str, position: int, text: str, chunk_id: str, content_hash: str):
        self.doc_id = doc_id
        self.position = position
        self.text = text
        self.chunk_id = chunk_id
        self.content_hash = content_hash


def chunk_document(doc_id: str, text: str, min_chars: int = 1) -> list[Chunk]:
    """Split a document into paragraph-level chunks.

    Paragraphs (blank-line-separated blocks) are the chunk granularity: they are small enough that an edit to one paragraph doesn't force re-embedding unrelated content, and large enough to carry meaningful retrieval context (unlike sentence-level splitting, which was rejected -- see README architecture section).
    """
    raw_paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[Chunk] = []
    position = 0
    for raw in raw_paragraphs:
        stripped = raw.strip()
        if len(stripped) < min_chars:
            continue
        cid = chunk_id(doc_id, position, stripped)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                position=position,
                text=stripped,
                chunk_id=cid,
                content_hash=content_hash(stripped),
            )
        )
        position += 1
    return chunks

document_path = r"Data\test1.txt"
doc_id = str(uuid.uuid4())
with open(document_path, "r", encoding="utf-8") as f:
    document_text = f.read()
chunks = chunk_document(doc_id, document_text)
for chunk in chunks:
    print(f"Chunk ID: {chunk.chunk_id}, Position: {chunk.position}, Content Hash: {chunk.content_hash}")
    print(f"Text: {chunk.text}\n\n\n\n\n\n")