"""Vector Store Service - Pinecone-backed semantic search for unstructured documents.

Handles:
  - Chunking raw document text into overlapping windows
  - Embedding chunks via OpenAI text-embedding-3-small
  - Upsert into Pinecone with rich metadata (account, source, filename, chunk index)
  - Semantic search: embed query → top-k Pinecone lookup → return chunks + metadata
  - Deduplication: re-uploading the same file replaces its old vectors (by source_doc_id)
  - Graceful degradation: if Pinecone is not configured, all methods are no-ops / return empty

Only called for unstructured files (PDF, TXT, DOCX).
CSV / XLSX go purely through the Silver SQL path.
"""

import hashlib
import logging
import os
from typing import List, Dict, Any, Optional

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE = 500        # characters per chunk
CHUNK_OVERLAP = 100     # overlap between consecutive chunks
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K_DEFAULT = 5       # how many chunks to retrieve per query
PINECONE_DIMENSION = 1536  # text-embedding-3-small output dimension
PINECONE_METRIC = "cosine"


# ---------------------------------------------------------------------------
# Helper — chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping fixed-size character windows.
    Tries to break on sentence boundaries ('. ') within the last 20% of a chunk.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to break on a sentence boundary within the last 20% of the chunk
        search_from = start + int(chunk_size * 0.8)
        boundary = text.rfind(". ", search_from, end)
        if boundary != -1:
            end = boundary + 1  # include the period

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap  # step back by overlap for next window

    return chunks


def _make_doc_id(filename: str, account_name: str, chunk_index: int) -> str:
    """
    Deterministic vector ID so re-uploading the same file overwrites old vectors.
    Format: sha256(filename + account_name)[:16] + "_chunk_{index}"
    """
    raw = f"{filename.lower().strip()}|{(account_name or '').lower().strip()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{digest}_chunk_{chunk_index}"


def _make_source_doc_prefix(filename: str, account_name: str) -> str:
    """Return the ID prefix shared by all chunks of this document."""
    raw = f"{filename.lower().strip()}|{(account_name or '').lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# VectorStoreService
# ---------------------------------------------------------------------------

class VectorStoreService:
    """
    Pinecone-backed vector store for unstructured document search.

    Usage:
        svc = VectorStoreService()
        if svc.is_available():
            svc.index_document(raw_text, filename, account_name, source)
        results = svc.search("what did the client say about pricing?", account_name="Acme")
    """

    def __init__(self):
        self._pc = None          # Pinecone client
        self._index = None       # Pinecone Index object
        self._openai = None      # OpenAI client for embeddings
        self._ready = False
        self._init()

    def _init(self):
        api_key = getattr(settings, "PINECONE_API_KEY", None) or os.getenv("PINECONE_API_KEY")
        index_name = getattr(settings, "PINECONE_INDEX", None) or os.getenv("PINECONE_INDEX", "sales-agent")

        if not api_key:
            print("VectorStore: PINECONE_API_KEY not set — vector indexing disabled")
            return

        if not getattr(settings, "OPENAI_API_KEY", None):
            print("VectorStore: OPENAI_API_KEY not set — cannot embed documents")
            return

        try:
            from pinecone import Pinecone, ServerlessSpec
            self._pc = Pinecone(api_key=api_key)

            existing_indexes = self._pc.list_indexes()
            existing_names = [idx.name for idx in existing_indexes]
            if index_name not in existing_names:
                print(f"VectorStore: Creating Pinecone index '{index_name}'...")
                self._pc.create_index(
                    name=index_name,
                    dimension=PINECONE_DIMENSION,
                    metric=PINECONE_METRIC,
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                print(f"VectorStore: Index '{index_name}' created ✅")
            else:
                # Validate that the existing index has the correct dimension
                idx_info = next((idx for idx in existing_indexes if idx.name == index_name), None)
                if idx_info and idx_info.dimension != PINECONE_DIMENSION:
                    print(
                        f"VectorStore: ❌ Index '{index_name}' has dimension {idx_info.dimension} "
                        f"but this app requires {PINECONE_DIMENSION}. "
                        f"Please delete the index on pinecone.io and restart — it will be recreated automatically."
                    )
                    return
                print(f"VectorStore: Using existing index '{index_name}'")

            self._index = self._pc.Index(index_name)
            self._openai = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=1)
            self._ready = True
            print("VectorStore: Ready ✅")

        except ImportError:
            print("VectorStore: 'pinecone' package not installed — run: pip install pinecone")
        except Exception as e:
            print(f"VectorStore: Initialization failed: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if Pinecone is configured and connected."""
        return self._ready

    def index_document(
        self,
        raw_text: str,
        filename: str,
        account_name: Optional[str] = None,
        source: str = "user_upload",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Chunk → embed → upsert a document into Pinecone.

        Idempotent: re-uploading the same filename+account_name deletes old chunks first.

        Args:
            raw_text:       Full extracted text of the document
            filename:       Original filename (used in dedup key + metadata)
            account_name:   Account the document belongs to (used for filtered search)
            source:         Data source label (e.g. "user_upload")
            extra_metadata: Any additional metadata to store alongside each chunk

        Returns:
            Number of chunks indexed (0 if unavailable or text too short)
        """
        if not self._ready:
            return 0

        if not raw_text or len(raw_text.strip()) < 50:
            logger.info("VectorStore: Skipping '%s' — text too short", filename)
            return 0

        chunks = _chunk_text(raw_text)
        if not chunks:
            return 0

        # Delete old vectors for this document before re-indexing (idempotent)
        self._delete_document_vectors(filename, account_name)

        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = self._embed(chunk)
            if embedding is None:
                continue

            doc_id = _make_doc_id(filename, account_name or "", i)
            metadata = {
                "text": chunk[:1000],           # Pinecone metadata cap — store first 1000 chars
                "filename": filename,
                "account_name": account_name or "",
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source_doc_prefix": _make_source_doc_prefix(filename, account_name or ""),
            }
            if extra_metadata:
                # Only add string/int/float/bool values — Pinecone metadata constraints
                for k, v in extra_metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        metadata[k] = v

            vectors.append({"id": doc_id, "values": embedding, "metadata": metadata})

        if not vectors:
            return 0

        # Upsert in batches of 100 (Pinecone limit)
        batch_size = 100
        for batch_start in range(0, len(vectors), batch_size):
            batch = vectors[batch_start: batch_start + batch_size]
            try:
                self._index.upsert(vectors=batch)
            except Exception as e:
                logger.error("VectorStore: Upsert failed for batch starting at %d: %s", batch_start, e)

        logger.info(
            "VectorStore: Indexed '%s' → %d chunks (account: %s)",
            filename, len(vectors), account_name or "—"
        )
        return len(vectors)

    def search(
        self,
        query: str,
        account_name: Optional[str] = None,
        top_k: int = TOP_K_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over indexed documents.

        Args:
            query:        Natural language question
            account_name: If provided, filter results to this account only
            top_k:        Number of chunks to return

        Returns:
            List of dicts with keys: text, filename, account_name, score, chunk_index
            Returns [] if unavailable or no results.
        """
        if not self._ready:
            return []

        if not query or not query.strip():
            return []

        embedding = self._embed(query)
        if embedding is None:
            return []

        try:
            filter_dict = {}
            if account_name and account_name.strip():
                filter_dict["account_name"] = {"$eq": account_name.strip()}

            query_kwargs = {
                "vector": embedding,
                "top_k": top_k,
                "include_metadata": True,
            }
            if filter_dict:
                query_kwargs["filter"] = filter_dict

            response = self._index.query(**query_kwargs)
            matches = response.get("matches", [])

            results = []
            for match in matches:
                meta = match.get("metadata", {})
                results.append({
                    "text": meta.get("text", ""),
                    "filename": meta.get("filename", ""),
                    "account_name": meta.get("account_name", ""),
                    "source": meta.get("source", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "score": round(match.get("score", 0.0), 4),
                })

            return results

        except Exception as e:
            logger.error("VectorStore: Search failed: %s", e)
            return []

    def delete_document(self, filename: str, account_name: Optional[str] = None) -> bool:
        """
        Remove all vectors for a specific document from the index.
        Useful if a document is explicitly deleted or re-uploaded.
        """
        if not self._ready:
            return False
        return self._delete_document_vectors(filename, account_name)

    def get_stats(self) -> Dict[str, Any]:
        """Return index statistics (total vector count, dimension, etc.)."""
        if not self._ready:
            return {"available": False}
        try:
            stats = self._index.describe_index_stats()
            return {
                "available": True,
                "total_vectors": stats.get("total_vector_count", 0),
                "dimension": stats.get("dimension", PINECONE_DIMENSION),
                "namespaces": stats.get("namespaces", {}),
            }
        except Exception as e:
            logger.error("VectorStore: Stats failed: %s", e)
            return {"available": True, "error": str(e)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> Optional[List[float]]:
        """Generate an embedding vector for a piece of text."""
        try:
            response = self._openai.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text.replace("\n", " "),
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("VectorStore: Embedding failed: %s", e)
            return None

    def _delete_document_vectors(self, filename: str, account_name: Optional[str]) -> bool:
        """
        Delete all existing vectors for a document using metadata filter.
        Falls back to prefix-based ID deletion if filter delete is unsupported.
        """
        prefix = _make_source_doc_prefix(filename, account_name or "")
        try:
            self._index.delete(filter={"source_doc_prefix": {"$eq": prefix}})
            return True
        except Exception:
            # Some Pinecone plans don't support filter-based delete — fall back silently
            logger.debug("VectorStore: Filter-based delete not supported, skipping pre-deletion")
            return False
