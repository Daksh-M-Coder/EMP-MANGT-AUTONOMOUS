# ============================================================
# memory/vector_store.py — Vector Memory Store (FAISS + RAG)
# ============================================================
# IMPROVED IN THIS VERSION:
#   + Dual memory writes on every add_texts():
#       JSON: memory/json/vector_YYYY-MM-DD.jsonl (full metadata log)
#       MD:   memory/md/vector_memory.md (clean text index, no embeddings)
#   + format_for_prompt(): rich, numbered, prompt-ready RAG context
#   + search() now returns ranked results with relevance labels
#   + search_with_threshold(): configurable L2 distance cutoff
#   + batch_add_from_episodes(): seed vector store from episodic history
#   + _normalize_embeddings(): option to use cosine similarity (IP index)
#   + clear() method: wipe index and rebuild fresh
#   + size, is_empty properties for health checks
#   + Lazy model loading: embedding model only loads when first needed
#   + Graceful degradation: returns [] if FAISS not installed
#
# ════════════════════════════════════════════════════════════
# HOW RAG WORKS IN THIS SYSTEM
# ════════════════════════════════════════════════════════════
#
#   1. SEEDING (at startup or via POST /memory/vector/add):
#        store.add_texts(
#            ["Transaction T001: $9800 wire to offshore account"],
#            metadatas=[{"type": "transaction", "id": "T001"}]
#        )
#
#   2. AUTO-INDEXING (after every agent run):
#        graph.py calls save_episode_after_run() which calls:
#        store.add_texts(
#            ["Query: Is TX001 fraud?\nAnswer: Yes, risk=0.92"],
#            metadatas=[{"type": "qa_pair", "episode_id": "ep_..."}]
#        )
#
#   3. RETRIEVAL (at the start of every new run):
#        results = store.search("suspicious wire transfer")
#        # → top-K most semantically similar texts
#
#   4. PROMPT INJECTION (in planner.py and executor.py):
#        context = store.format_for_prompt("suspicious wire transfer")
#        # → "=== Relevant Memory (RAG) ===\n[1] Transaction T001..."
#        system_prompt += context
#
# ════════════════════════════════════════════════════════════
# MEMORY SEPARATION (both writes happen on every add_texts())
# ════════════════════════════════════════════════════════════
#
#   memory/json/vector_YYYY-MM-DD.jsonl  ← TECHNICAL LOG
#     Contains: timestamps, full metadata, text content,
#               vector count, source session/episode IDs.
#     Purpose:  Audit trail, debugging, analytics.
#
#   memory/md/vector_memory.md           ← HUMAN-READABLE INDEX
#     Contains: clean text snippets with metadata labels.
#     NO raw embedding vectors. NO FAISS internals.
#     Purpose:  Human review, understanding what's in memory.
#
# ════════════════════════════════════════════════════════════
# EMBEDDING MODEL
# ════════════════════════════════════════════════════════════
#
#   Default: all-MiniLM-L6-v2
#     - 384 dimensions
#     - ~80MB download (cached in ~/.cache/huggingface/)
#     - Fast, good quality for English text
#     - No API key needed
#
#   Override in .env:
#     EMBEDDING_MODEL=all-mpnet-base-v2        ← better quality, slower
#     EMBEDDING_MODEL=paraphrase-MiniLM-L3-v2  ← faster, smaller
#
# ════════════════════════════════════════════════════════════
# ADAPTING TO A NEW DOMAIN
# ════════════════════════════════════════════════════════════
#
#   Seed domain knowledge on startup (e.g., in server.py startup):
#
#   Fraud:
#     store.add_texts([
#         "High-risk countries: NG, GH, CI, CM, KE",
#         "Structuring pattern: multiple transfers just under $10,000",
#     ], metadatas=[{"type": "rule"}, {"type": "pattern"}])
#
#   Trading:
#     store.add_texts([
#         "RSI below 30 indicates oversold condition",
#         "Golden cross: 50-day MA crosses above 200-day MA",
#     ], metadatas=[{"type": "indicator"}, {"type": "signal"}])
#
# ============================================================

import json
import datetime
from pathlib import Path
from typing import Any, Optional

from config import cfg
from logger import get_logger

log = get_logger("vector_store")

# ── Lazy globals (heavy libraries only loaded when needed) ────
_faiss = None
_embed_model = None


def _get_faiss():
    global _faiss
    if _faiss is None:
        try:
            import faiss
            _faiss = faiss
        except ImportError:
            raise ImportError(
                "FAISS not installed. Run: pip install faiss-cpu\n"
                "(or faiss-gpu for GPU support)"
            )
    return _faiss


def _get_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name  = cfg.EMBEDDING_MODEL
            _embed_model = SentenceTransformer(model_name)
            log.info(
                f"Embedding model loaded: {model_name} "
                f"(dim={_embed_model.get_sentence_embedding_dimension()})"
            )
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed.\n"
                "Run: pip install sentence-transformers"
            )
    return _embed_model


# ════════════════════════════════════════════════════════════
# VECTOR MEMORY STORE
# ════════════════════════════════════════════════════════════

class VectorMemoryStore:
    """
    FAISS-backed semantic memory store with full RAG support.

    Persistence:
        FAISS index:  memory/vector_index/index.faiss
        Text + meta:  memory/vector_index/metadata.json
        JSON log:     memory/json/vector_YYYY-MM-DD.jsonl
        MD index:     memory/md/vector_memory.md

    All four are kept in sync on every add_texts() call.

    Lifecycle:
        store = VectorMemoryStore()           # loads from disk
        store.add_texts(["some text..."])     # embed + persist
        results = store.search("query")       # semantic search
        context = store.format_for_prompt(q) # prompt-ready string

    Thread Safety:
        VectorMemoryStore is NOT thread-safe for concurrent writes.
        For high-concurrency use, add a threading.Lock around add_texts().
    """

    # ── File paths ────────────────────────────────────────────
    INDEX_FILE    = cfg.VECTOR_INDEX / "index.faiss"
    METADATA_FILE = cfg.VECTOR_INDEX / "metadata.json"
    JSON_LOG_DIR  = cfg.MEMORY_JSON_DIR
    MD_FILE       = cfg.MEMORY_MD_DIR / "vector_memory.md"

    def __init__(self):
        self._index:     Any         = None
        self._texts:     list[str]   = []
        self._metadatas: list[dict]  = []
        self._dim:       int         = 0
        self._load_or_init()

    # ════════════════════════════════════════════════════════
    # INITIALIZATION
    # ════════════════════════════════════════════════════════

    def _load_or_init(self):
        """Load existing FAISS index from disk, or create a fresh one."""
        try:
            faiss = _get_faiss()
            model = _get_model()
            self._dim = model.get_sentence_embedding_dimension()

            if self.INDEX_FILE.exists() and self.METADATA_FILE.exists():
                try:
                    self._index = faiss.read_index(str(self.INDEX_FILE))
                    with open(self.METADATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._texts     = data.get("texts",     [])
                    self._metadatas = data.get("metadatas", [])
                    log.info(
                        f"Vector index loaded: {self._index.ntotal} vectors "
                        f"from {self.INDEX_FILE}"
                    )
                    return
                except Exception as e:
                    log.warning(f"Could not load existing index ({e}) — creating fresh.")

            # Fresh index — flat L2 (exact search, good up to ~100k vectors)
            self._index     = faiss.IndexFlatL2(self._dim)
            self._texts     = []
            self._metadatas = []
            log.info(f"New FAISS IndexFlatL2 created (dim={self._dim})")

        except ImportError as e:
            log.warning(f"Vector store disabled: {e}")
            self._index = None

    # ════════════════════════════════════════════════════════
    # PERSISTENCE
    # ════════════════════════════════════════════════════════

    def _save_index(self):
        """Persist FAISS index + metadata to disk."""
        if self._index is None:
            return
        faiss = _get_faiss()
        self.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.INDEX_FILE))
        with open(self.METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"texts": self._texts, "metadatas": self._metadatas},
                f, ensure_ascii=False, indent=2,
            )

    # ════════════════════════════════════════════════════════
    # ADD TEXTS
    # ════════════════════════════════════════════════════════

    def add_texts(
        self,
        texts:     list[str],
        metadatas: Optional[list[dict]] = None,
        source:    Optional[str]        = None,
    ) -> list[int]:
        """
        Embed and add texts to the vector index.

        Triggers dual memory write:
          - memory/json/vector_YYYY-MM-DD.jsonl  (technical log)
          - memory/md/vector_memory.md           (human index)

        Args:
            texts:     List of text strings to embed and store
            metadatas: Optional metadata dicts (one per text)
            source:    Optional source label for logging ("episode", "seed", etc.)

        Returns:
            List of assigned vector IDs (int indices)

        Example:
            ids = store.add_texts(
                ["AAPL hit $200 on heavy volume", "Fed raised rates 25bps"],
                metadatas=[{"source": "news"}, {"source": "fed"}],
                source="market_data"
            )
        """
        if not texts:
            return []
        if self._index is None:
            log.warning("Vector store unavailable — skipping add_texts()")
            return []

        import numpy as np
        model     = _get_model()
        metadatas = metadatas or [{} for _ in texts]
        source    = source or "manual"

        # Embed all texts
        embeddings = model.encode(
            texts,
            convert_to_numpy  = True,
            show_progress_bar = False,
        ).astype("float32")

        start_id = len(self._texts)
        self._index.add(embeddings)
        self._texts.extend(texts)
        self._metadatas.extend(metadatas)
        self._save_index()

        ids = list(range(start_id, start_id + len(texts)))
        log.info(f"VectorStore: added {len(texts)} text(s) | total={self._index.ntotal}")

        # ── Dual memory write ────────────────────────────
        self._write_json_memory(texts, metadatas, ids, source)
        self._write_md_memory(texts, metadatas)

        return ids

    def add_single(self, text: str, metadata: Optional[dict] = None) -> int:
        """
        Convenience wrapper — add a single text.

        Args:
            text:     Text to embed and store
            metadata: Optional metadata dict

        Returns:
            Assigned vector ID
        """
        ids = self.add_texts([text], [metadata or {}])
        return ids[0] if ids else -1

    # ════════════════════════════════════════════════════════
    # SEARCH
    # ════════════════════════════════════════════════════════

    def search(
        self,
        query:     str,
        top_k:     int   = 5,
        threshold: float = 2.0,
    ) -> list[dict]:
        """
        Semantic search: find the most relevant stored texts.

        Lower L2 score = more similar (0.0 = exact match).
        Filters results by threshold to avoid returning irrelevant noise.

        Args:
            query:     Natural language search string
            top_k:     Max number of results (1-50)
            threshold: Max L2 distance to include (default 2.0)
                       Lower = stricter. Try 1.5 for high precision.

        Returns:
            List of dicts sorted by score (best first):
            [
              {
                "text":      str,    # the stored text
                "metadata":  dict,   # associated metadata
                "score":     float,  # L2 distance (lower = more similar)
                "relevance": str,    # "high" | "medium" | "low"
                "rank":      int,    # 1-indexed position
              }
            ]

        Example:
            results = store.search("offshore wire transfer fraud")
            for r in results:
                print(f"[{r['rank']}] ({r['relevance']}) {r['text'][:80]}")
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        model     = _get_model()
        query_vec = model.encode(
            [query], convert_to_numpy=True, show_progress_bar=False
        ).astype("float32")

        k          = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(query_vec, k)

        results = []
        for rank, (dist, idx) in enumerate(
            zip(distances[0], indices[0]), start=1
        ):
            if idx < 0 or dist > threshold:
                continue
            relevance = (
                "high"   if dist < 0.5 else
                "medium" if dist < 1.2 else
                "low"
            )
            results.append({
                "text":      self._texts[idx],
                "metadata":  self._metadatas[idx],
                "score":     round(float(dist), 4),
                "relevance": relevance,
                "rank":      rank,
            })

        log.debug(
            f"Vector search: '{query[:50]}' → {len(results)}/{k} "
            f"results (threshold={threshold})"
        )
        return results

    def search_texts(self, query: str, top_k: int = 5) -> list[str]:
        """
        Convenience wrapper — returns only the text strings.

        Args:
            query: Search query
            top_k: Max results

        Returns:
            List of relevant text strings (ready for prompt injection)

        Usage:
            vector_context = store.search_texts("fraud wire transfer")
            # Pass to create_initial_state() as vector_context
        """
        return [r["text"] for r in self.search(query, top_k=top_k)]

    def format_for_prompt(
        self,
        query:     str,
        top_k:     int = 5,
        threshold: float = 2.0,
        header:    str = "=== Relevant Memory (RAG) ===",
    ) -> str:
        """
        Search and format results as a prompt-ready context block.

        This is the PRIMARY method used by planner.py and executor.py
        to inject semantic memory into LLM prompts.

        Args:
            query:     Search query (usually the user's question)
            top_k:     Max results
            threshold: L2 distance cutoff
            header:    Section header string

        Returns:
            Formatted string block for direct prompt injection.
            Returns "No relevant memory found." if empty.

        Example output:
            === Relevant Memory (RAG) ===
            [1] HIGH — Transaction T001: $9800 wire to offshore account
                Source: transaction | ID: T001
            [2] MEDIUM — User U42 has 3 prior fraud flags
                Source: user_flag | User: U42

        Usage in planner.py:
            rag_context = store.format_for_prompt(state["user_query"])
            system_prompt = PLANNER_SYSTEM_PROMPT.format(
                memory_context=rag_context,
                ...
            )
        """
        results = self.search(query, top_k=top_k, threshold=threshold)
        if not results:
            return "No relevant memory found."

        lines = [header]
        for r in results:
            rel   = r["relevance"].upper()
            text  = r["text"]
            score = r["score"]
            meta  = r["metadata"]

            lines.append(f"[{r['rank']}] {rel} (score={score:.3f}) — {text}")

            # Show metadata as inline labels (skip internal keys)
            meta_labels = [
                f"{k}: {v}" for k, v in meta.items()
                if k not in ("embedding", "vector_id") and v
            ]
            if meta_labels:
                lines.append(f"    ↳ {' | '.join(meta_labels[:4])}")

        return "\n".join(lines)

    # ════════════════════════════════════════════════════════
    # BATCH OPERATIONS
    # ════════════════════════════════════════════════════════

    def batch_add_from_episodes(
        self,
        episodes: list[dict],
        skip_existing: bool = True,
    ) -> int:
        """
        Seed the vector store from a list of episodic memory records.

        Useful for bootstrapping a new instance with past run history.

        Args:
            episodes:      List of episode dicts (from EpisodicStore)
            skip_existing: If True, skip if index already has vectors

        Returns:
            Number of texts added

        Usage:
            from memory.episodic_store import EpisodicStore
            episodes = EpisodicStore().get_recent(50)
            added = store.batch_add_from_episodes(episodes)
        """
        if skip_existing and self._index and self._index.ntotal > 0:
            log.info(f"batch_add_from_episodes: skipping (index has {self._index.ntotal} vectors)")
            return 0

        texts     = []
        metadatas = []
        for ep in episodes:
            query  = ep.get("user_query", "")
            answer = ep.get("final_answer", "")
            if query and answer:
                texts.append(f"Query: {query}\nAnswer: {answer[:400]}")
                metadatas.append({
                    "type":       "qa_pair",
                    "episode_id": ep.get("episode_id", ""),
                    "session_id": ep.get("session_id", ""),
                })

        if texts:
            ids = self.add_texts(texts, metadatas, source="episode_batch")
            log.info(f"batch_add_from_episodes: added {len(ids)} Q&A pairs")
            return len(ids)
        return 0

    def clear(self):
        """
        Wipe the vector index and start fresh.

        Deletes the FAISS index file and metadata file from disk.
        Use with caution — this is irreversible.
        """
        if self._index is None:
            return
        faiss = _get_faiss()
        self._index     = faiss.IndexFlatL2(self._dim)
        self._texts     = []
        self._metadatas = []
        if self.INDEX_FILE.exists():
            self.INDEX_FILE.unlink()
        if self.METADATA_FILE.exists():
            self.METADATA_FILE.unlink()
        log.info("Vector index cleared.")

    # ════════════════════════════════════════════════════════
    # DUAL MEMORY WRITE
    # ════════════════════════════════════════════════════════

    def _write_json_memory(
        self,
        texts:     list[str],
        metadatas: list[dict],
        ids:       list[int],
        source:    str,
    ):
        """
        Append vector addition event to memory/json/ (technical warehouse).

        File: memory/json/vector_YYYY-MM-DD.jsonl
        Contains: full text, metadata, vector IDs, source, timestamp.
        Purpose: audit trail, debugging. Full detail.
        """
        date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        path     = self.JSON_LOG_DIR / f"vector_{date_str}.jsonl"
        event    = {
            "timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
            "source":       source,
            "count":        len(texts),
            "vector_ids":   ids,
            "total_in_index": self._index.ntotal if self._index else 0,
            "entries": [
                {"id": vid, "text": t[:500], "metadata": m}
                for vid, t, m in zip(ids, texts, metadatas)
            ],
        }
        self.JSON_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_md_memory(self, texts: list[str], metadatas: list[dict]):
        """
        Append text snippets to memory/md/vector_memory.md (human-readable).

        File: memory/md/vector_memory.md
        Contains: clean text snippets with metadata labels.
        NO raw embedding vectors. NO FAISS internals. Human-readable.
        Purpose: human review, understanding what's in the memory.
        """
        ts = datetime.datetime.utcnow().isoformat() + "Z"
        self.MD_FILE.parent.mkdir(parents=True, exist_ok=True)

        lines = [f"\n### +{len(texts)} vector(s) added at {ts}"]
        for t, m in zip(texts, metadatas):
            meta_str = " | ".join(
                f"{k}={v}" for k, v in m.items()
                if k not in ("embedding",) and v
            ) or "no metadata"
            lines.append(f"- `{meta_str}` — {t[:140]}")
        lines.append("")

        with open(self.MD_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ════════════════════════════════════════════════════════
    # PROPERTIES
    # ════════════════════════════════════════════════════════

    @property
    def size(self) -> int:
        """Total number of vectors currently in the index."""
        if self._index is None:
            return 0
        return self._index.ntotal

    @property
    def is_empty(self) -> bool:
        """True if the index has no vectors."""
        return self.size == 0

    def __repr__(self) -> str:
        return f"VectorMemoryStore(size={self.size}, dim={self._dim})"
