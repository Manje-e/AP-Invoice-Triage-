import os
import re
import psycopg2
import psycopg2.extras
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Policy Documents ───────────────────────────────────────────────────────────
# Each entry: (doc_name, doc_title, filepath)
# Filepaths are relative — run this script from the project root.
POLICY_DOCS = [
    ("FIN-POL-001",  "Invoice Approval and Payment Policy",
     "invoice_approval_policy.md"),
    ("FIN-POL-002",  "Invoice Fraud Detection Guidelines",
     "fraud_detection_guidelines.md"),
    ("PROC-POL-001", "Vendor Onboarding, Management, and Compliance Guidelines",
     "vendor_guidelines.md"),
]


# ── Text Extraction ────────────────────────────────────────────────────────────

def extract_pdf(filepath: str) -> str:
    """Extract all text from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(filepath)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def extract_docx(filepath: str) -> str:
    """Extract all paragraph text from a DOCX using python-docx."""
    from docx import Document
    doc = Document(filepath)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(filepath: str) -> str:
    """Route to the correct extractor based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return extract_pdf(filepath)
    elif ext == ".docx":
        return extract_docx(filepath)
    else:
        # Plain text / markdown fallback
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()


# ── Chunking Strategy ──────────────────────────────────────────────────────────
# Split on numbered section headings (e.g. "1. PURPOSE", "3.2 PO Matching").
# This works for both PDFs and DOCX since the heading text is preserved after
# extraction. Each chunk = one logical section. Min 100 chars to skip stubs.

HEADING_PATTERN = re.compile(
    r'(?=\n\s*\d+[\.\d]*\s+[A-Z][^\n]{3,})',  # matches \n then "3.2 HEADING TEXT"
    re.MULTILINE
)

def chunk_by_headings(text: str) -> list[str]:
    """
    Split extracted text on numbered section headings.
    Falls back to fixed-size chunks if no headings are found.
    """
    parts = HEADING_PATTERN.split(text)
    chunks = []
    for part in parts:
        cleaned = part.strip()
        if len(cleaned) >= 100:
            chunks.append(cleaned)

    # Fallback: if heading split produced nothing useful, chunk by size
    if len(chunks) <= 1:
        chunks = chunk_by_size(text)

    return chunks


def chunk_by_size(text: str, size: int = 1000, overlap: int = 100) -> list[str]:
    """
    Fixed-size chunking with overlap. Used as fallback only.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end].strip()
        if len(chunk) >= 100:
            chunks.append(chunk)
        start += size - overlap
    return chunks


# ── Embedding ──────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# ── DB Connection ──────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


# ── Ingest ─────────────────────────────────────────────────────────────────────

def ingest():
    print("=" * 55)
    print("RAG Ingest — Policy Documents")
    print("=" * 55)

    conn = get_connection()

    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks")
        print("Cleared existing document_chunks.\n")
    conn.commit()

    total_chunks = 0

    for doc_name, doc_title, filepath in POLICY_DOCS:
        print(f"Processing {doc_name}: {doc_title}")

        # Extract text from PDF / DOCX / txt
        text = extract_text(filepath)
        print(f"  Extracted {len(text)} chars")

        # Chunk
        chunks = chunk_by_headings(text)
        print(f"  {len(chunks)} chunks found")

        # Embed and insert
        with conn.cursor() as cur:
            for i, chunk in enumerate(chunks):
                embedding = get_embedding(chunk)
                cur.execute("""
                    INSERT INTO document_chunks
                        (doc_name, doc_title, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    doc_name,
                    doc_title,
                    i,
                    chunk,
                    embedding
                ))
                print(f"  Chunk {i} inserted ({len(chunk)} chars)")
                total_chunks += 1

        conn.commit()
        print(f"  ✓ {doc_name} done\n")

    conn.close()
    print(f"✅ Ingest complete. {total_chunks} chunks inserted into document_chunks.")


if __name__ == "__main__":
    ingest()
