import os
import json
import base64
import fitz  # PyMuPDF
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── GPT-4o Vision Extraction ───────────────────────────────────────────────────
def extract_with_gpt4o(file_bytes: bytes, media_type: str) -> dict:
    """
    Send image or scanned PDF page to GPT-4o Vision.
    Returns structured invoice fields as a dict.
    """
    base64_image = base64.b64encode(file_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": """Extract the following fields from this invoice image and return ONLY a valid JSON object with no extra text or markdown:
{
  "vendor_name": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "amount": number or null,
  "department": "string or null",
  "approver": "string or null",
  "description": "string or null"
}
If a field is not found in the invoice, set it to null.
For amount, return only the numeric value without currency symbols."""
                }
            ]
        }]
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── PyMuPDF Text Extraction ────────────────────────────────────────────────────
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Try to extract text from a PDF using PyMuPDF.
    Returns extracted text or empty string if none found.
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception:
        return ""


# ── Parse Text into Fields ─────────────────────────────────────────────────────
def parse_fields_from_text(text: str) -> dict:
    """
    Send extracted PDF text to GPT-4o to parse into structured fields.
    Cheaper than vision — just text completion, no image needed.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Extract the following fields from this invoice text and return ONLY a valid JSON object with no extra text or markdown:
{{
  "vendor_name": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "amount": number or null,
  "department": "string or null",
  "approver": "string or null",
  "description": "string or null"
}}
If a field is not found, set it to null.
For amount, return only the numeric value without currency symbols.

Invoice text:
{text[:3000]}"""
        }]
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── Main Extraction Function ───────────────────────────────────────────────────
def decide_and_extract(file_bytes: bytes, filename: str) -> dict:
    """
    Main entry point. Decides extraction strategy based on file type.
    
    Flow:
    - JPG/PNG → straight to GPT-4o Vision
    - PDF → try PyMuPDF first
              → if text found → parse with GPT-4o text (cheaper)
              → if no text (scanned) → GPT-4o Vision on first page
    
    Returns dict with extracted fields or None if extraction failed.
    """
    ext = filename.lower().split(".")[-1]

    # ── Image file → straight to GPT-4o Vision ────────────────────────────────
    if ext in ["jpg", "jpeg", "png"]:
        media_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
        print(f"[Extractor] Image file detected — sending to GPT-4o Vision")
        return extract_with_gpt4o(file_bytes, media_type)

    # ── PDF file → try PyMuPDF first ──────────────────────────────────────────
    if ext == "pdf":
        print(f"[Extractor] PDF detected — trying PyMuPDF first")
        text = extract_text_from_pdf(file_bytes)

        if len(text) >= 50:
            # Good text extracted — parse with GPT-4o text (no vision needed)
            print(f"[Extractor] Text extracted ({len(text)} chars) — parsing with GPT-4o text")
            result = parse_fields_from_text(text)
            if result and result.get("amount") and result.get("vendor_name"):
                return result
            print(f"[Extractor] Text parsing failed — falling back to GPT-4o Vision")

        # No text or parsing failed — scanned PDF, use Vision on first page
        print(f"[Extractor] No usable text — sending to GPT-4o Vision")
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        image_bytes = pix.tobytes("png")
        doc.close()
        return extract_with_gpt4o(image_bytes, "image/png")

    return None
