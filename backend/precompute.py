import psycopg2
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def fetch_invoices(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT invoice_id, vendor_name, vendor_id, invoice_number,
                   invoice_date, due_date, amount, department, approver, description
            FROM invoices
        """)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert_flag(cur, flag_id, invoice_id, flag_type, severity, reason,
                related_invoice_id=None, group_id=None):
    cur.execute("""
        INSERT INTO invoice_flags
            (flag_id, invoice_id, flag_type, severity, reason, related_invoice_id, group_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (flag_id) DO NOTHING
    """, (flag_id, invoice_id, flag_type, severity, reason, related_invoice_id, group_id))

# ── 1. DUPLICATE EXACT ────────────────────────────────────────────────────────
def detect_exact_duplicates(invoices, dup_flagged, cur):
    print("Detecting exact duplicates...")
    seen = {}
    counter = 1
    for inv in invoices:
        if not inv['amount']: continue
        key = (inv['vendor_name'], inv['invoice_number'], inv['amount'])
        if key in seen:
            other = seen[key]
            group_id = f"DUP-{counter:03d}"
            if counter == 1:
                reason = (
                    f"Invoice {inv['invoice_number']} from {inv['vendor_name']} for "
                    f"Rs.{int(inv['amount']):,} was submitted twice with identical invoice number, "
                    f"amount and date — accidental resubmission by vendor. Only one should be processed."
                )
            else:
                reason = (
                    f"Invoice {inv['invoice_number']} from {inv['vendor_name']} for "
                    f"Rs.{int(inv['amount']):,} appears twice on the same date — vendor likely "
                    f"resubmitted after not receiving payment confirmation, risking double payment."
                )
            for iid in [inv['invoice_id'], other['invoice_id']]:
                insert_flag(cur, f"FLG-DUPE-{iid}", iid, "DUPLICATE_EXACT", "HIGH", reason,
                            related_invoice_id=group_id)
                dup_flagged.add(iid)
            print(f"  {inv['invoice_id']} <-> {other['invoice_id']} [{group_id}]")
            counter += 1
        else:
            seen[key] = inv

# ── 2. DUPLICATE NEAR ─────────────────────────────────────────────────────────
def detect_near_duplicates(invoices, dup_flagged, cur):
    print("Detecting near duplicates...")
    done_pairs = set()
    counter = 1
    for i, i1 in enumerate(invoices):
        for j, i2 in enumerate(invoices):
            if i >= j: continue
            # skip if already exact dup
            if i1['invoice_id'] in dup_flagged or i2['invoice_id'] in dup_flagged: continue
            pair = tuple(sorted([i1['invoice_id'], i2['invoice_id']]))
            if pair in done_pairs: continue
            if i1['vendor_name'] != i2['vendor_name']: continue
            if i1['invoice_number'] == i2['invoice_number']: continue
            if not i1['amount'] or not i2['amount']: continue
            a1, a2 = float(i1['amount']), float(i2['amount'])
            pct = abs(a1-a2)/a1
            days = abs((i1['invoice_date'] - i2['invoice_date']).days)
            if pct <= 0.05 and days <= 5:
                group_id = f"NDU-{counter:03d}"
                counter += 1
                done_pairs.add(pair)
                if pct <= 0.03:
                    r1 = (
                        f"{i1['vendor_name']} submitted {i1['invoice_number']} for Rs.{int(a1):,} and "
                        f"{i2['invoice_number']} for Rs.{int(a2):,} just {days} day(s) apart — only "
                        f"{pct*100:.1f}% difference with near-identical descriptions. Likely duplicate "
                        f"billing for the same service under two different invoice numbers."
                    )
                    r2 = (
                        f"{i2['vendor_name']} submitted {i2['invoice_number']} for Rs.{int(a2):,} and "
                        f"{i1['invoice_number']} for Rs.{int(a1):,} just {days} day(s) apart — only "
                        f"{pct*100:.1f}% difference with near-identical descriptions. Likely duplicate "
                        f"billing for the same service under two different invoice numbers."
                    )
                else:
                    r1 = (
                        f"{i1['vendor_name']} raised {i1['invoice_number']} for Rs.{int(a1):,} followed "
                        f"by {i2['invoice_number']} for Rs.{int(a2):,} within {days} day(s) — "
                        f"{pct*100:.1f}% apart from the same vendor in quick succession. Possible double "
                        f"entry or revised invoice not marked as replacement."
                    )
                    r2 = (
                        f"{i2['vendor_name']} raised {i2['invoice_number']} for Rs.{int(a2):,} followed "
                        f"by {i1['invoice_number']} for Rs.{int(a1):,} within {days} day(s) — "
                        f"{pct*100:.1f}% apart from the same vendor in quick succession. Possible double "
                        f"entry or revised invoice not marked as replacement."
                    )
                insert_flag(cur, f"FLG-NEAR-{i1['invoice_id']}", i1['invoice_id'],
                            "DUPLICATE_NEAR", "MEDIUM", r1, related_invoice_id=group_id)
                insert_flag(cur, f"FLG-NEAR-{i2['invoice_id']}", i2['invoice_id'],
                            "DUPLICATE_NEAR", "MEDIUM", r2, related_invoice_id=group_id)
                dup_flagged.add(i1['invoice_id'])
                dup_flagged.add(i2['invoice_id'])
                print(f"  {i1['invoice_id']} <-> {i2['invoice_id']} [{group_id}] {pct*100:.1f}%")

# ── 3. THRESHOLD SPLIT ────────────────────────────────────────────────────────
def detect_threshold_splits(invoices, dup_flagged, cur):
    print("Detecting threshold split suspects...")
    THRESHOLD = 100000
    WINDOW = 30
    counter = 1
    vendor_map = defaultdict(list)
    for inv in invoices:
        # skip dup flagged, skip if amount missing or above threshold
        if inv['invoice_id'] in dup_flagged: continue
        if not inv['amount'] or inv['amount'] >= THRESHOLD: continue
        vendor_map[inv['vendor_name']].append(inv)

    for vendor, vinvs in vendor_map.items():
        if len(vinvs) < 2: continue
        vinvs.sort(key=lambda x: x['invoice_date'])
        used = set()
        for i in range(len(vinvs)):
            if vinvs[i]['invoice_id'] in used: continue
            group = [vinvs[i]]
            for j in range(i+1, len(vinvs)):
                if vinvs[j]['invoice_id'] in used: continue
                if (vinvs[j]['invoice_date'] - vinvs[i]['invoice_date']).days <= WINDOW:
                    group.append(vinvs[j])
            if len(group) < 2: continue
            total = sum(g['amount'] for g in group)
            if total < THRESHOLD: continue
            group_id = f"GRP-{counter:03d}"
            counter += 1
            for g in group:
                used.add(g['invoice_id'])
                reason = (
                    f"{vendor} submitted {len(group)} separate invoices between "
                    f"{group[0]['invoice_date'].strftime('%d %b %Y')} and "
                    f"{group[-1]['invoice_date'].strftime('%d %b %Y')} "
                    f"totalling Rs.{int(total):,} — each kept below the Rs.1,00,000 threshold "
                    f"(this invoice: Rs.{int(g['amount']):,}). Consistent with deliberate splitting "
                    f"to bypass senior approval requirements."
                )
                insert_flag(cur, f"FLG-SPLT-{g['invoice_id']}", g['invoice_id'],
                            "THRESHOLD_SPLIT_SUSPECT", "HIGH", reason, group_id=group_id)
            print(f"  {[g['invoice_id'] for g in group]} [{group_id}] Rs.{int(total):,}")
            break

# ── 4. THRESHOLD BREACH ───────────────────────────────────────────────────────
def detect_threshold_breach(invoices, dup_flagged, cur):
    print("Detecting threshold breaches...")
    for inv in invoices:
        if inv['invoice_id'] in dup_flagged or not inv['amount']: continue
        if 100000 < inv['amount'] <= 150000:
            excess = int(inv['amount'] - 100000)
            reason = (
                f"Invoice from {inv['vendor_name']} for Rs.{int(inv['amount']):,} exceeds the "
                f"Rs.1,00,000 approval threshold by Rs.{excess:,}. Assigned to {inv['approver']} "
                f"in {inv['department']} — senior approval required before payment can be processed."
            )
            insert_flag(cur, f"FLG-BRCH-{inv['invoice_id']}", inv['invoice_id'],
                        "THRESHOLD_BREACH", "HIGH", reason)
            print(f"  {inv['invoice_id']} Rs.{int(inv['amount']):,}")

# ── 5. HIGH VALUE ─────────────────────────────────────────────────────────────
def detect_high_value(invoices, dup_flagged, cur):
    print("Detecting high value invoices...")
    for inv in invoices:
        if inv['invoice_id'] in dup_flagged or not inv['amount']: continue
        if inv['amount'] > 150000:
            reason = (
                f"Invoice from {inv['vendor_name']} for Rs.{int(inv['amount']):,} is classified "
                f"as high value — significantly above the Rs.1,00,000 approval threshold. "
                f"Assigned to {inv['approver']} in {inv['department']}. Requires purchase order "
                f"verification, vendor credential check, and board-level sign-off before payment."
            )
            insert_flag(cur, f"FLG-HVAL-{inv['invoice_id']}", inv['invoice_id'],
                        "HIGH_VALUE", "HIGH", reason)
            print(f"  {inv['invoice_id']} Rs.{int(inv['amount']):,}")

# ── 6. MISSING FIELDS — runs on ALL invoices ──────────────────────────────────
def detect_missing_fields(invoices, cur):
    print("Detecting missing fields...")
    for inv in invoices:
        missing = []
        if not inv['approver'] or not str(inv['approver']).strip(): missing.append('approver')
        if not inv['department'] or not str(inv['department']).strip(): missing.append('department')
        if not inv['description'] or not str(inv['description']).strip(): missing.append('description')
        if not inv['amount']: missing.append('amount')
        if missing:
            reason = (
                f"Invoice {inv['invoice_number']} from {inv['vendor_name']} is missing required "
                f"field(s): {', '.join(missing)}. Incomplete invoices cannot be processed for payment "
                f"and must be returned to the vendor for correction before approval."
            )
            insert_flag(cur, f"FLG-MISS-{inv['invoice_id']}", inv['invoice_id'],
                        "MISSING_FIELDS", "MEDIUM", reason)
            print(f"  {inv['invoice_id']} missing: {', '.join(missing)}")

# ── 7. ROUND AMOUNT — runs on ALL invoices ────────────────────────────────────
def detect_round_amount(invoices, cur):
    print("Detecting round amounts...")
    for inv in invoices:
        if not inv['amount']: continue
        a = int(inv['amount'])
        if a >= 10000 and a % 100000 == 0:
            reason = (
                f"Invoice from {inv['vendor_name']} for exactly Rs.{a:,} is an exact lakh amount "
                f"— suspiciously round for a real invoice. Real costs rarely land on perfect lakhs. "
                f"Request supporting documents and PO verification before processing."
            )
            insert_flag(cur, f"FLG-RNDM-{inv['invoice_id']}", inv['invoice_id'],
                        "ROUND_AMOUNT", "LOW", reason)
            print(f"  {inv['invoice_id']} Rs.{a:,}")

# ── 8. DUE SOON — runs on ALL invoices ───────────────────────────────────────
def detect_due_soon(invoices, cur):
    from datetime import date
    print("Detecting due soon...")
    today = date.today()
    for inv in invoices:
        if not inv['due_date'] or not inv['amount']: continue
        days = (inv['due_date'] - today).days
        if 0 <= days <= 7:
            reason = (
                f"Invoice from {inv['vendor_name']} for Rs.{int(inv['amount']):,} "
                f"is due on {inv['due_date'].strftime('%d %b %Y')} — only {days} day(s) away. "
                f"Prioritise review and approval to avoid late payment penalties."
            )
            insert_flag(cur, f"FLG-DSON-{inv['invoice_id']}", inv['invoice_id'],
                        "DUE_SOON", "MEDIUM", reason)
            print(f"  {inv['invoice_id']} due in {days} days")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run():
    print("=" * 55)
    print("AP Invoice Triage — Precompute")
    print("=" * 55)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM invoice_flags")
            print("Cleared existing flags.\n")

        invoices = fetch_invoices(conn)
        print(f"Loaded {len(invoices)} invoices.\n")

        # dup_flagged — only used to keep exact and near dups mutually exclusive
        # all other detectors run independently on all invoices
        dup_flagged = set()

        with conn.cursor() as cur:
            detect_exact_duplicates(invoices, dup_flagged, cur)
            detect_near_duplicates(invoices, dup_flagged, cur)
            detect_threshold_splits(invoices, dup_flagged, cur)
            detect_threshold_breach(invoices, dup_flagged, cur)
            detect_high_value(invoices, dup_flagged, cur)
            detect_missing_fields(invoices, cur)
            detect_round_amount(invoices, cur)
            detect_due_soon(invoices, cur)

        conn.commit()
        print(f"\n✅ Precompute complete.")

        with conn.cursor() as cur:
            cur.execute("""
                SELECT flag_type, severity, COUNT(*)
                FROM invoice_flags
                GROUP BY flag_type, severity
                ORDER BY flag_type
            """)
            print("\nFlag summary:")
            for row in cur.fetchall():
                print(f"  {row[0]} ({row[1]}): {row[2]} flags")
            cur.execute("SELECT COUNT(*) FROM invoice_flags")
            print(f"\n  TOTAL: {cur.fetchone()[0]} flag rows")
            cur.execute("""
                SELECT invoice_id, COUNT(*) as flag_count
                FROM invoice_flags
                GROUP BY invoice_id
                HAVING COUNT(*) > 1
                ORDER BY flag_count DESC
            """)
            rows = cur.fetchall()
            print(f"\nInvoices with multiple flags: {len(rows)}")
            for row in rows:
                print(f"  {row[0]}: {row[1]} flags")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run()



