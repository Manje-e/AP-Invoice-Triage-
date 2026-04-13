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


# ── Text Quality Check ────────────────────────────────────────────────────────
def is_useful_text(text: str) -> bool:
    """
    Returns True only if extracted PDF text looks like real invoice content.
    Prevents sending garbled OCR or header-only text to GPT-4o text parse.

    Rules:
    - Must be at least 80 characters
    - Must have at least 5 non-empty lines (not just whitespace/headers)
    - Must contain at least one numeric pattern (likely an amount or date)
    - Must not be more than 80% non-ASCII (garbled scan artifact)
    """
    if len(text) < 80:
        return False

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 5:
        return False

    import re
    if not re.search(r'\d{2,}', text):  # at least one number with 2+ digits
        return False

    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii / len(text) > 0.8:
        return False

    return True


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
    IMAGE_TYPES = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "tiff": "image/tiff",
        "tif": "image/tiff",
    }
    if ext in IMAGE_TYPES:
        # TIFF not supported by OpenAI Vision API — convert to PNG first
        if ext in ["tiff", "tif"]:
            print(f"[Extractor] TIFF detected — converting to PNG for Vision API")
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(file_bytes))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            file_bytes = buf.getvalue()
            media_type = "image/png"
        else:
            media_type = IMAGE_TYPES[ext]
        print(f"[Extractor] Image file ({ext}) detected — sending to GPT-4o Vision")
        return extract_with_gpt4o(file_bytes, media_type)

    # ── PDF file → try PyMuPDF first ──────────────────────────────────────────
    if ext == "pdf":
        print(f"[Extractor] PDF detected — trying PyMuPDF first")
        text = extract_text_from_pdf(file_bytes)

        if is_useful_text(text):
            # Quality check passed — parse with GPT-4o text (no vision needed)
            print(f"[Extractor] Text quality check passed ({len(text)} chars) — parsing with GPT-4o text")
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
