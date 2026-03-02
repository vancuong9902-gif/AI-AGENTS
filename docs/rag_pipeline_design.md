# Retrieval-Augmented Generation (RAG) Pipeline Design

## 1) Architecture Diagram (Text)

```text
[PDF Files]
    |
    v
[PDF Loader + Text Cleaner]
    |  (normalize unicode, remove headers/footers, keep page metadata)
    v
[Chunker]
    |  (semantic-aware chunks + overlap)
    v
[Embedding Model]
    |  (batch embedding vectors)
    v
[ChromaDB Collection]
    |  (id, embedding, chunk_text, source, page, section)
    |
    +-----------------------------+
                                  |
User Question ----------------> [Query Embedder]
                                  |
                                  v
                          [Top-K Retriever (k=5)]
                                  |
                                  v
                      [Re-ranker / Similarity Filter]
                                  |  (drop weak matches)
                                  v
                           [Prompt Builder]
                                  |  (context + citations + guardrails)
                                  v
                               [LLM]
                                  |
                                  v
                     [Answer + Citation References]
```

---

## 2) Chunking Strategy

**Goals:** preserve meaning, improve retrieval precision, and keep chunk sizes compatible with the LLM context window.

1. **Split first by document structure**
   - Prefer sections/headings and paragraphs (instead of fixed-size blind splitting).
   - Attach metadata: `source_file`, `page`, `section_title`, `chunk_index`.

2. **Token-aware chunking**
   - Target chunk size: **350-500 tokens**.
   - Overlap: **60-100 tokens** to preserve context across boundaries.

3. **Heuristics**
   - Keep tables/lists together where possible.
   - Avoid crossing section boundaries unless a section is very short.
   - Remove noisy boilerplate repeated on every page (e.g., page headers).

4. **Quality checks before indexing**
   - Deduplicate near-identical chunks.
   - Skip chunks that are too short (e.g., `< 40 tokens`) unless they are titles/definitions.

---

## 3) Embedding Strategy

1. **Model choice**
   - Use a strong sentence embedding model for retrieval (examples):
     - `sentence-transformers/all-MiniLM-L6-v2` (fast, lightweight), or
     - `BAAI/bge-small-en-v1.5` (strong retrieval quality).

2. **Consistency rule**
   - **Use the exact same embedding model** for indexing and query embedding.

3. **Batching + normalization**
   - Embed in batches (e.g., 32-128 chunks per batch).
   - Normalize vectors (`L2`) for cosine similarity stability.

4. **Metadata-rich storage in ChromaDB**
   - Store:
     - `id`
     - `embedding`
     - `document` (chunk text)
     - `metadatas`: `{source, page, section, chunk_index}`

5. **Retrieval configuration**
   - Retrieve **top 5** chunks (`k=5`).
   - Optional: apply a minimum similarity threshold (e.g., `score >= 0.72`) to reduce hallucinations.

---

## 4) Code Example (Python)

```python
from typing import List, Dict
import os
import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# ---------- Config ----------
PDF_PATH = "./data/handbook.pdf"
CHROMA_DIR = "./chroma_store"
COLLECTION_NAME = "pdf_knowledge"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

# ---------- 1) Load PDF ----------
def load_pdf_pages(pdf_path: str) -> List[Dict]:
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = " ".join(text.split())  # light cleanup
        pages.append({"page": i, "text": text, "source": os.path.basename(pdf_path)})
    return pages

# ---------- 2) Chunk ----------
def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    # Simple character-based fallback chunking.
    # In production, prefer token-aware splitting (350-500 tokens, 60-100 overlap).
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks

# ---------- 3) Build embeddings + store in Chroma ----------
def index_pdf(pdf_path: str):
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    pages = load_pdf_pages(pdf_path)
    ids, docs, metas = [], [], []

    for p in pages:
        page_chunks = chunk_text(p["text"])
        for j, ch in enumerate(page_chunks):
            chunk_id = f"{p['source']}-p{p['page']}-c{j}"
            ids.append(chunk_id)
            docs.append(ch)
            metas.append({"source": p["source"], "page": p["page"], "chunk_index": j})

    embeddings = model.encode(docs, normalize_embeddings=True).tolist()

    # Upsert into Chroma
    collection.upsert(
        ids=ids,
        documents=docs,
        embeddings=embeddings,
        metadatas=metas,
    )

# ---------- 4) Retrieve top-5 ----------
def retrieve(query: str, k: int = TOP_K):
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=COLLECTION_NAME)

    q_emb = model.encode([query], normalize_embeddings=True).tolist()[0]
    result = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    return result

# ---------- 5) Prompt injection + anti-hallucination ----------
def build_prompt(question: str, retrieved: Dict) -> str:
    docs = retrieved["documents"][0]
    metas = retrieved["metadatas"][0]
    distances = retrieved["distances"][0]

    context_blocks = []
    citations = []

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances), start=1):
        # Convert distance to rough confidence (depends on metric/model)
        context_blocks.append(
            f"[CTX-{i}] source={meta['source']} page={meta['page']} score={1 - dist:.3f}\n{doc}"
        )
        citations.append(f"[{i}] {meta['source']} p.{meta['page']}")

    context = "\n\n".join(context_blocks)
    citation_text = "\n".join(citations)

    prompt = f"""
You are a grounded assistant. Use only the provided context.
If the context is insufficient, say: "I don't have enough evidence in the provided documents."
Do not invent facts. Every key claim must cite at least one source id like [1], [2], etc.

User question:
{question}

Context:
{context}

Citations map:
{citation_text}

Return format:
1) Direct answer
2) Evidence bullets with citations
3) If uncertain, state the missing information
""".strip()

    return prompt

# Example usage:
# index_pdf(PDF_PATH)
# r = retrieve("What are the data retention rules?")
# prompt = build_prompt("What are the data retention rules?", r)
# print(prompt)
```

---

## 5) Hallucination Prevention Checklist

1. **Grounded prompt policy**
   - "Use only provided context."
   - "If missing evidence, explicitly say insufficient context."

2. **Retrieval thresholding**
   - If top chunks are below similarity threshold, return "insufficient evidence".

3. **Citation-required output schema**
   - Force each claim to include references like `[1]`, `[2]` tied to source/page metadata.

4. **Post-generation validation (recommended)**
   - Validate each citation id exists in retrieved context.
   - Optional: run claim-vs-evidence checker before returning final response.

5. **No-context fallback**
   - If retriever returns empty/weak results, do not call free-form answering mode.

---

## 6) Citation Reference Format

Recommended format in final answer:
- Inline claim citation: `... according to policy [2].`
- Reference section:
  - `[1] handbook.pdf, page 3`
  - `[2] handbook.pdf, page 7`
  - `[3] handbook.pdf, page 12`

This keeps responses auditable and helps users verify each statement quickly.
