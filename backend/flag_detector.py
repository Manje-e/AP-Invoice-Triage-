import os
import psycopg2
import psycopg2.extras
from datetime import date, timedelta

# ── Flag Severity Map ──────────────────────────────────────────────────────────
FLAG_SEVERITY = {
    "DUPLICATE_EXACT": "HIGH",
    "DUPLICATE_NEAR": "MEDIUM",
    "THRESHOLD_SPLIT_SUSPECT": "HIGH",
    "THRESHOLD_BREACH": "HIGH",
    "HIGH_VALUE": "HIGH",
    "MISSING_FIELDS": "MEDIUM",
    "ROUND_AMOUNT": "LOW",
    "DUE_SOON": "MEDIUM"
}

# ── Insert Flag ────────────────────────────────────────────────────────────────
def insert_flag(cur, flag_id, invoice_id, flag_type, reason, related_invoice_id=None, group_id=None):
    severity = FLAG_SEVERITY.get(flag_type, "MEDIUM")
    cur.execute("""
        INSERT INTO invoice_flags 
            (flag_id, invoice_id, flag_type, severity, reason, related_invoice_id, group_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (flag_id) DO NOTHING
    """, (flag_id, invoice_id, flag_type, severity, reason, related_invoice_id, group_id))


# ── Check DUPLICATE_EXACT ──────────────────────────────────────────────────────
def check_duplicate_exact(cur, invoice):
    cur.execute("""
        SELECT invoice_id FROM invoices
        WHERE vendor_id = %s
          AND invoice_number = %s
          AND amount = %s
          AND invoice_date = %s
          AND invoice_id != %s
    """, (invoice["vendor_id"], invoice["invoice_number"],
          invoice["amount"], invoice["invoice_date"], invoice["invoice_id"]))

    matches = cur.fetchall()
    if matches:
        group_id = f"DUP-NEW-{invoice['invoice_id']}"
        reason = (f"Invoice {invoice['invoice_number']} from {invoice['vendor_name']} "
                  f"for Rs.{invoice['amount']:,.0f} appears to be an exact duplicate.")

        insert_flag(cur,
            flag_id=f"FLG-DUPE-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="DUPLICATE_EXACT",
            reason=reason,
            related_invoice_id=group_id
        )

        # Also flag the matching invoice if not already flagged
        for match in matches:
            insert_flag(cur,
                flag_id=f"FLG-DUPE-{match['invoice_id']}",
                invoice_id=match["invoice_id"],
                flag_type="DUPLICATE_EXACT",
                reason=reason,
                related_invoice_id=group_id
            )
        return True
    return False


# ── Check DUPLICATE_NEAR ───────────────────────────────────────────────────────
def check_duplicate_near(cur, invoice):
    cur.execute("""
        SELECT invoice_id, amount, invoice_number FROM invoices
        WHERE vendor_id = %s
          AND invoice_number != %s
          AND ABS(invoice_date - %s::date) <= 5
          AND invoice_id != %s
    """, (invoice["vendor_id"], invoice["invoice_number"],
          invoice["invoice_date"], invoice["invoice_id"]))

    for match in cur.fetchall():
        diff = abs(float(invoice["amount"]) - float(match["amount"]))
        pct = diff / float(match["amount"]) if float(match["amount"]) > 0 else 1
        if pct <= 0.05:
            group_id = f"NDU-NEW-{invoice['invoice_id']}"
            reason = (f"Invoice from {invoice['vendor_name']} is similar to "
                      f"{match['invoice_number']} — amount within 5% and submitted within 5 days.")

            insert_flag(cur,
                flag_id=f"FLG-NEAR-{invoice['invoice_id']}",
                invoice_id=invoice["invoice_id"],
                flag_type="DUPLICATE_NEAR",
                reason=reason,
                related_invoice_id=group_id
            )
            insert_flag(cur,
                flag_id=f"FLG-NEAR-{match['invoice_id']}",
                invoice_id=match["invoice_id"],
                flag_type="DUPLICATE_NEAR",
                reason=reason,
                related_invoice_id=group_id
            )
            return True
    return False


# ── Check THRESHOLD_SPLIT ──────────────────────────────────────────────────────
def check_threshold_split(cur, invoice):
    if float(invoice["amount"]) >= 100000:
        return False  # not a split candidate

    cur.execute("""
        SELECT i.invoice_id, i.amount FROM invoices i
        WHERE i.vendor_id = %s
          AND i.amount < 100000
          AND i.invoice_id != %s
          AND ABS(i.invoice_date - %s::date) <= 30
          AND i.invoice_id NOT IN (
              SELECT invoice_id FROM invoice_flags 
              WHERE flag_type = 'DUPLICATE_EXACT' OR flag_type = 'DUPLICATE_NEAR'
          )
    """, (invoice["vendor_id"], invoice["invoice_id"], invoice["invoice_date"]))

    related = cur.fetchall()
    if related:
        total = float(invoice["amount"]) + sum(float(r["amount"]) for r in related)
        if total > 100000:
            group_id = f"GRP-NEW-{invoice['invoice_id']}"
            reason = (f"{invoice['vendor_name']} submitted multiple invoices within 30 days. "
                      f"Combined total Rs.{total:,.0f} exceeds the Rs.1,00,000 threshold.")

            insert_flag(cur,
                flag_id=f"FLG-SPLT-{invoice['invoice_id']}",
                invoice_id=invoice["invoice_id"],
                flag_type="THRESHOLD_SPLIT_SUSPECT",
                reason=reason,
                group_id=group_id
            )
            for r in related:
                insert_flag(cur,
                    flag_id=f"FLG-SPLT-{r['invoice_id']}",
                    invoice_id=r["invoice_id"],
                    flag_type="THRESHOLD_SPLIT_SUSPECT",
                    reason=reason,
                    group_id=group_id
                )
            return True
    return False


# ── Check THRESHOLD_BREACH ─────────────────────────────────────────────────────
def check_threshold_breach(cur, invoice):
    amount = float(invoice["amount"])
    if 100000 <= amount <= 150000:
        reason = (f"Invoice from {invoice['vendor_name']} for Rs.{amount:,.0f} "
                  f"exceeds the Rs.1,00,000 approval threshold and requires senior sign-off.")
        insert_flag(cur,
            flag_id=f"FLG-BRCH-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="THRESHOLD_BREACH",
            reason=reason
        )
        return True
    return False


# ── Check HIGH_VALUE ───────────────────────────────────────────────────────────
def check_high_value(cur, invoice):
    amount = float(invoice["amount"])
    if amount > 150000:
        reason = (f"Invoice from {invoice['vendor_name']} for Rs.{amount:,.0f} "
                  f"is a high value invoice exceeding Rs.1,50,000 and requires board-level approval.")
        insert_flag(cur,
            flag_id=f"FLG-HIGH-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="HIGH_VALUE",
            reason=reason
        )
        return True
    return False


# ── Check MISSING_FIELDS ───────────────────────────────────────────────────────
def check_missing_fields(cur, invoice):
    missing = []
    if not invoice.get("approver") or str(invoice["approver"]).strip() == "":
        missing.append("approver")
    if not invoice.get("department") or str(invoice["department"]).strip() == "":
        missing.append("department")
    if not invoice.get("description") or str(invoice["description"]).strip() == "":
        missing.append("description")

    if missing:
        reason = (f"Invoice from {invoice['vendor_name']} is missing required fields: "
                  f"{', '.join(missing)}. Cannot process until corrected.")
        insert_flag(cur,
            flag_id=f"FLG-MISS-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="MISSING_FIELDS",
            reason=reason
        )
        return True
    return False


# ── Check ROUND_AMOUNT ─────────────────────────────────────────────────────────
def check_round_amount(cur, invoice):
    amount = float(invoice["amount"])
    if amount >= 10000 and amount % 100000 == 0:
        reason = (f"Invoice from {invoice['vendor_name']} for Rs.{amount:,.0f} "
                  f"is an exact lakh amount — suspiciously round for a real invoice. Request supporting documents and PO verification.")
        insert_flag(cur,
            flag_id=f"FLG-RUND-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="ROUND_AMOUNT",
            reason=reason
        )
        return True
    return False


# ── Check DUE_SOON ─────────────────────────────────────────────────────────────
def check_due_soon(cur, invoice):
    if not invoice.get("due_date"):
        return False
    today = date.today()
    due = invoice["due_date"] if isinstance(invoice["due_date"], date) else date.fromisoformat(str(invoice["due_date"]))
    days_left = (due - today).days
    if 0 <= days_left <= 7:
        reason = (f"Invoice from {invoice['vendor_name']} is due in {days_left} days "
                  f"({due}). Prioritise for approval.")
        insert_flag(cur,
            flag_id=f"FLG-DUES-{invoice['invoice_id']}",
            invoice_id=invoice["invoice_id"],
            flag_type="DUE_SOON",
            reason=reason
        )
        return True
    return False


# ── Main: Run All Flag Checks on One Invoice ───────────────────────────────────
def run_flag_detection(invoice_id: str, conn) -> list:
    """
    Runs all 8 flag checks on a single invoice.
    Called after a new invoice is inserted via upload.
    Returns list of flag types that were detected.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

        # Fetch the invoice
        cur.execute("SELECT * FROM invoices WHERE invoice_id = %s", (invoice_id,))
        invoice = dict(cur.fetchone())

        if not invoice:
            return []

        flags_detected = []

        # Run all checks
        # Note: MISSING_FIELDS and ROUND_AMOUNT run on all invoices freely
        # Duplicate checks run first — if exact duplicate found, skip split check

        is_exact_dup = check_duplicate_exact(cur, invoice)
        is_near_dup = check_duplicate_near(cur, invoice)

        if not is_exact_dup and not is_near_dup:
            if check_threshold_split(cur, invoice):
                flags_detected.append("THRESHOLD_SPLIT_SUSPECT")

        if is_exact_dup:
            flags_detected.append("DUPLICATE_EXACT")
        if is_near_dup:
            flags_detected.append("DUPLICATE_NEAR")

        amount = float(invoice["amount"]) if invoice.get("amount") else 0

        if not is_exact_dup and not is_near_dup:
            if amount > 150000:
                if check_high_value(cur, invoice):
                    flags_detected.append("HIGH_VALUE")
            elif 100000 <= amount <= 150000:
                if check_threshold_breach(cur, invoice):
                    flags_detected.append("THRESHOLD_BREACH")

        if check_missing_fields(cur, invoice):
            flags_detected.append("MISSING_FIELDS")

        if check_round_amount(cur, invoice):
            flags_detected.append("ROUND_AMOUNT")

        if check_due_soon(cur, invoice):
            flags_detected.append("DUE_SOON")

        conn.commit()

    return flags_detected
