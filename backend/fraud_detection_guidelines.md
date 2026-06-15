Invoice Fraud Detection and Prevention Guidelines

Policy Number: FIN-POL-002 | Version: v1.3 | Effective Date: 01 January 2026
Approved By: CFO, Internal Audit Committee | Classification: Internal — Strictly Confidential

---

1. Purpose

This document provides guidelines for identifying, investigating, and escalating potentially fraudulent or suspicious invoices at Investors Ltd. Finance staff and approvers must familiarise themselves with these guidelines and apply them during invoice processing.

---

2. Scope

These guidelines apply to all invoices received from external vendors and contractors. They apply to all Finance staff, departmental approvers, and the Internal Audit team.

---

3.1 Exact Duplicate Invoices — DUPLICATE_EXACT Flag

An exact duplicate invoice is flagged as DUPLICATE_EXACT when two or more invoices from the same vendor have an identical invoice number, identical amount, and the same invoice date.

Risk: Double payment to vendor. Could be accidental resubmission or deliberate fraud attempt.

Indicators:
- Same vendor name
- Same invoice number
- Same amount
- Same or very close invoice date

Required action for DUPLICATE_EXACT invoices:
1. Hold both invoices immediately — do not process either
2. Contact vendor to confirm which invoice is valid
3. Cancel the duplicate in the system
4. Document the incident in the fraud log
5. If deliberate, escalate to Internal Audit

---

3.2 Near Duplicate Invoices — DUPLICATE_NEAR Flag

A near duplicate invoice is flagged as DUPLICATE_NEAR when two invoices from the same vendor have different invoice numbers but amounts within 5% of each other, submitted within 5 days of each other.

Risk: Possible double billing for the same service under different invoice numbers.

Indicators:
- Same vendor
- Different invoice numbers
- Amount difference of 5% or less
- Submitted within 5 calendar days
- Similar or identical descriptions

Required action for DUPLICATE_NEAR invoices:
1. Flag both invoices for review
2. Contact vendor to clarify if these are separate legitimate charges
3. Request supporting documentation for both
4. Do not pay either until confirmed legitimate
5. If one is a replacement, cancel the original and process the replacement only

---

3.3 Threshold Splitting — THRESHOLD_SPLIT_SUSPECT Flag

Invoice splitting fraud occurs when a vendor submits multiple invoices within a 30-day window, each individually below Rs.1,00,000, but whose combined total exceeds Rs.1,00,000. This pattern is flagged as THRESHOLD_SPLIT_SUSPECT.

Risk: Deliberate attempt to bypass senior approval requirements. This is a serious control violation.

Indicators:
- Same vendor
- Multiple invoices within 30 days
- Each individual invoice below Rs.1,00,000
- Combined total of all invoices in the group exceeds Rs.1,00,000
- Similar descriptions across invoices

Required action for THRESHOLD_SPLIT_SUSPECT invoices:
1. Treat the entire group as a single transaction
2. Escalate to senior approver regardless of individual invoice amounts
3. Request a consolidated purchase order covering the full combined amount
4. If splitting appears deliberate, escalate to Internal Audit immediately
5. Document all invoices in the group with their combined total

---

3.4 Round Amount Invoices — ROUND_AMOUNT Flag

A round amount invoice is flagged as ROUND_AMOUNT when the invoice amount is an exact multiple of Rs.1,00,000. Real costs rarely land on exact lakh amounts. This may indicate estimated or fabricated billing.

Note: ROUND_AMOUNT is a separate flag from HIGH_VALUE. A round amount invoice is not necessarily a high value invoice, and a high value invoice is not necessarily a round amount.

Required action for ROUND_AMOUNT invoices:
1. Request full itemised breakdown from vendor
2. Verify against Purchase Order
3. Do not approve without supporting documentation

---

3.5 Missing Fields — MISSING_FIELDS Flag

An invoice is flagged as MISSING_FIELDS when it is missing one or more mandatory fields — specifically approver, department, or description.

Risk: Incomplete invoices cannot be properly verified or audited. A missing approver field may indicate an attempt to process without proper authorisation.

Required action for MISSING_FIELDS invoices:
1. Reject immediately and return to vendor
2. Do not enter into payment system
3. Notify the departmental approver that their vendor submitted an incomplete invoice

---

4.1 Initial Review

When a suspicious invoice is identified:
1. Place a hold on the invoice — no payment to be processed
2. Document the suspicion with specific reasons
3. Notify the Finance Manager within 24 hours

---

4.2 Vendor Contact

Finance must contact the vendor in writing requesting clarification. All correspondence must be saved. Verbal confirmations are not acceptable — written confirmation required.

---

4.3 Escalation to Internal Audit

The following must be escalated to Internal Audit immediately:
- Any confirmed duplicate invoice where both were paid
- Any vendor found to be deliberately splitting invoices (THRESHOLD_SPLIT_SUSPECT confirmed)
- Any invoice where the approver cannot be verified
- Any invoice where vendor credentials cannot be confirmed

---

4.4 Documentation

All suspicious invoice incidents must be logged in the Fraud Incident Register. The log must include invoice details, nature of suspicion, actions taken, resolution, and escalation status.

---

5.1 Risky Vendor Definition

A vendor is classified as risky if they have any exact duplicate invoice (DUPLICATE_EXACT flag), any near duplicate invoice (DUPLICATE_NEAR flag), or any threshold splitting flag (THRESHOLD_SPLIT_SUSPECT flag) against them. These are the fraud-pattern flags that indicate deliberate or suspicious billing behaviour.

---

5.2 Vendor Review Threshold

A vendor with 3 or more flags of any type across all their invoices must be referred to the Vendor Management team for a full review. Finance must not process further invoices from that vendor until the review is complete.

---

5.3 Vendor Suspension

The CFO may suspend a vendor pending investigation. During suspension no invoices from that vendor may be processed regardless of approval status.

---

6. Responsibilities

- Finance Staff: First line detection, flagging, hold placement
- Departmental Approver: Verify invoice legitimacy before forwarding
- Finance Manager: Review flagged invoices, authorise escalation
- Internal Audit: Investigate escalated cases, maintain fraud register
- CFO: Final authority on vendor suspension and board escalation

---

7. Policy Violations

Any employee who knowingly approves a suspicious invoice, fails to report a suspected duplicate, or interferes with fraud investigation will be subject to immediate disciplinary action and potential legal proceedings.

Investors Ltd — Finance & Accounts Department — FIN-POL-002 v1.3 — Internal — Strictly Confidential
