import os
import psycopg2
import psycopg2.extras
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── DB Connection ──────────────────────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


# ── Embed Query ────────────────────────────────────────────────────────────────
def embed_query(text: str) -> list[float]:
    """
    Embeds the user's question using the same model used during ingest.
    Must match — text-embedding-3-small → 1536 dimensions.
    """
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# ── Search ─────────────────────────────────────────────────────────────────────
def search_documents(query: str, top_k: int = 4) -> str:
    """
    Main retrieval function. Called by the RAG node in langgraph_agent.py.

    Steps:
    1. Embed the query
    2. Cosine similarity search against document_chunks
    3. Return top_k chunks as a single formatted string

    Returns a string ready to be injected into a GPT prompt.
    """
    embedding = embed_query(query)

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    doc_name,
                    doc_title,
                    content,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM document_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (embedding, embedding, top_k))

            rows = cur.fetchall()

    finally:
        conn.close()

    if not rows:
        return "No relevant policy documents found."

    # Format chunks into a clean string for the GPT prompt
    parts = []
    for i, row in enumerate(rows):
        parts.append(
            f"[{i+1}] Source: {row['doc_name']} — {row['doc_title']}\n"
            f"Similarity: {row['similarity']:.3f}\n"
            f"{row['content']}"
        )

    return "\n\n---\n\n".join(parts)
