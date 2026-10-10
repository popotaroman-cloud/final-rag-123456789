import re
import threading
from dataclasses import dataclass

import numpy as np

from . import config, ollama_client

# nomic-embed-text was trained with these task prefixes; using them noticeably
# improves retrieval quality. Other embedding models simply ignore them.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    doc_id: str
    heading: str
    text: str


def _split_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading, lines = "", []
    for line in content.splitlines():
        match = _HEADING.match(line)
        if match:
            if any(l.strip() for l in lines):
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = match.group(2).strip(), []
        else:
            lines.append(line)
    if any(l.strip() for l in lines):
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def _windows(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            if cut != -1:
                end = cut
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_document(doc_id: str, content: str) -> list[Chunk]:
    chunks = []
    for heading, body in _split_sections(content):
        for piece in _windows(body, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
            text = f"{heading}\n{piece}" if heading else piece
            chunks.append(Chunk(doc_id=doc_id, heading=heading, text=text))
    return chunks


class _Namespace:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectors = np.zeros((0, 0), dtype=np.float32)


class KnowledgeStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spaces: dict[str, _Namespace] = {}

    def add(self, namespace: str, documents: list[tuple[str, str]]) -> int:
        new_chunks = [c for doc_id, content in documents for c in chunk_document(doc_id, content)]
        if not new_chunks:
            return 0
        raw = ollama_client.embed([DOC_PREFIX + c.text for c in new_chunks])
        vectors = np.asarray(raw, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10

        replaced = {doc_id for doc_id, _ in documents}
        with self._lock:
            space = self._spaces.setdefault(namespace, _Namespace())
            keep = [i for i, c in enumerate(space.chunks) if c.doc_id not in replaced]
            kept_chunks = [space.chunks[i] for i in keep]
            kept_vectors = space.vectors[keep] if keep else np.zeros((0, vectors.shape[1]), np.float32)
            space.chunks = kept_chunks + new_chunks
            space.vectors = np.vstack([kept_vectors, vectors])
        return len(new_chunks)

    def delete(self, namespace: str) -> bool:
        with self._lock:
            return self._spaces.pop(namespace, None) is not None

    def search(self, namespace: str | None, query: str, k: int) -> list[tuple[Chunk, float]]:
        if not namespace:
            return []
        with self._lock:
            space = self._spaces.get(namespace)
            if space is None or not space.chunks:
                return []
            chunks, vectors = list(space.chunks), space.vectors.copy()
        q = np.asarray(ollama_client.embed([QUERY_PREFIX + query])[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-10
        scores = vectors @ q
        top = np.argsort(-scores)[:k]
        return [(chunks[i], float(scores[i])) for i in top]
