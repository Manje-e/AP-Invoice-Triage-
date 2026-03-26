import os
import uuid
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from agent import run_agent
from extractor import decide_and_extract
from flag_detector import run_flag_detection

load_dotenv()

app = FastAPI(title="AP Invoice Triage API")

# Allow requests from Streamlit UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB Connection ─────────────────────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}

# ── Load Invoice Batch ────────────────────────────────────────────────────────
@app.get("/load-batch")
def load_batch():
    """
    Called when user clicks Load Invoice Batch.
    Returns summary stats for the dashboard cards and charts.
    No agent involved — direct Supabase queries.
    """
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Total invoices and spend
            cur.execute("""
                SELECT 
                    COUNT(*) as total_invoices,
                    COALESCE(SUM(amount), 0) as total_spend
                FROM invoices
            """)
            summary = dict(cur.fetchone())

            # Total flagged invoices (distinct)
            cur.execute("""
                SELECT COUNT(DISTINCT invoice_id) as total_flagged
                FROM invoice_flags
            """)
            flagged = dict(cur.fetchone())

            # Flag breakdown by type
            cur.execute("""
                SELECT flag_type, COUNT(*) as count
                FROM invoice_flags
                GROUP BY flag_type
                ORDER BY count DESC
            """)
            flag_breakdown = [dict(row) for row in cur.fetchall()]

            # Spend by department
            cur.execute("""
                SELECT department, COALESCE(SUM(amount), 0) as spend
                FROM invoices
                WHERE department IS NOT NULL AND department != ''
                GROUP BY department
                ORDER BY spend DESC
            """)
            dept_spend = [dict(row) for row in cur.fetchall()]

            # Top vendors by invoice count
            cur.execute("""
                SELECT vendor_name, COUNT(*) as invoice_count, 
                       COALESCE(SUM(amount), 0) as total_amount
                FROM invoices
                GROUP BY vendor_name
                ORDER BY invoice_count DESC
                LIMIT 5
            """)
            top_vendors = [dict(row) for row in cur.fetchall()]

            # All invoices with their flag (if any) for dashboard table
            cur.execute("""
                SELECT 
                    i.invoice_id, i.vendor_name, i.amount, i.due_date,
                    i.department, i.approver,
                    f.flag_type
                FROM invoices i
                LEFT JOIN invoice_flags f ON i.invoice_id = f.invoice_id
                ORDER BY i.invoice_id
            """)
            all_invoices = [dict(row) for row in cur.fetchall()]

        conn.close()

        total = int(summary['total_invoices'])
        flagged_count = int(flagged['total_flagged'])
        total_spend = float(summary['total_spend'])

        return {
            "batch_info": {
                "period": "Jan - Feb 2026",
                "total_invoices": total,
                "total_flagged": flagged_count,
                "clear_invoices": total - flagged_count,
                "total_spend": total_spend,
                "currency": "INR"
            },
            "flag_breakdown": flag_breakdown,
            "dept_spend": dept_spend,
            "top_vendors": top_vendors,
            "all_invoices": all_invoices,
            "message": (
                f"Invoice batch loaded. {total} invoices found for Jan-Feb 2026, "
                f"totalling Rs.{total_spend:,.0f}. "
                f"{flagged_count} invoices have been flagged for review. "
                f"Ask me anything about this batch!"
            )
        }

    except Exception as e:
        return {"error": str(e)}

# ── Upload Invoice ────────────────────────────────────────────────────────────
@app.post("/upload-invoice")
async def upload_invoice(file: UploadFile = File(...)):
    """
    Called when user uploads a PDF or photo invoice.
    Flow:
    1. Read file bytes
    2. Extract fields using extractor.py (PyMuPDF or GPT-4o Vision)
    3. Generate new invoice_id
    4. Insert into invoices table
    5. Run flag detection on the new invoice
    6. Return success with extracted fields and any flags detected
    """
    try:
        # Read file
        file_bytes = await file.read()
        filename = file.filename

        # Check file type
        ext = filename.lower().split(".")[-1]
        if ext not in ["pdf", "jpg", "jpeg", "png"]:
            return {"error": "Unsupported file type. Please upload PDF, JPG, or PNG only."}

        # Extract fields
        extracted = decide_and_extract(file_bytes, filename)

        if not extracted:
            return {"error": "Could not extract invoice details. Please try a clearer image or PDF."}

        if not extracted.get("vendor_name") or not extracted.get("amount"):
            return {"error": "Could not find vendor name or amount in the invoice. Please try again."}

        # Generate new invoice_id
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Get next invoice number
            cur.execute("SELECT COUNT(*) as total FROM invoices")
            total = cur.fetchone()["total"]
            new_invoice_id = f"INV-{str(total + 1).zfill(3)}"

            # Generate a vendor_id from vendor name
            vendor_id = "VND-" + extracted["vendor_name"][:4].upper().replace(" ", "")

            # Insert into invoices table
            cur.execute("""
                INSERT INTO invoices (
                    invoice_id, vendor_name, vendor_id, invoice_number,
                    invoice_date, due_date, amount, currency,
                    department, approver, description, status
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (invoice_id) DO NOTHING
            """, (
                new_invoice_id,
                extracted.get("vendor_name"),
                vendor_id,
                extracted.get("invoice_number"),
                extracted.get("invoice_date"),
                extracted.get("due_date"),
                extracted.get("amount"),
                "INR",
                extracted.get("department"),
                extracted.get("approver"),
                extracted.get("description"),
                "pending"
            ))
            conn.commit()

        # Run flag detection on the new invoice
        flags_detected = run_flag_detection(new_invoice_id, conn)
        conn.close()

        return {
            "success": True,
            "invoice_id": new_invoice_id,
            "extracted": extracted,
            "flags_detected": flags_detected,
            "message": (
                f"Invoice {new_invoice_id} from {extracted.get('vendor_name')} "
                f"added successfully! "
                + (f"Flags detected: {', '.join(flags_detected)}" if flags_detected else "No flags detected — clear to pay.")
            )
        }

    except Exception as e:
        return {"error": str(e)}

# ── Triage ────────────────────────────────────────────────────────────────────
class Query(BaseModel):
    question: str
    conversation_history: list = []

@app.post("/triage")
def triage(query: Query):
    """
    Called when user submits a question in the chat.
    Passes question to agent which calls LLM → SQL tool → LLM → answer.
    """
    try:
        result = run_agent(
            user_question=query.question,
            conversation_history=query.conversation_history
        )
        return {
            "answer": result.get("answer", ""),
            "data": result.get("data", None)
        }
    except Exception as e:
        return {
            "answer": "Sorry, I ran into an issue processing your question. Please try again.",
            "data": None,
            "error": str(e)
        }
