import os
import json
from typing import TypedDict, Literal
from openai import OpenAI
from langgraph.graph import StateGraph, END
from tools import execute_sql
from rag_retriever import search_documents
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ══════════════════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    question:             str
    conversation_history: list
    route:                str        # "sql" | "rag" | "both"
    sql_result:           dict | None
    rag_result:           str  | None
    answer:               str  | None


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

ROUTER_PROMPT = """
You are a routing assistant for an AP Invoice Triage system.
Your only job is to classify the user's question into one of three routes.

Routes:
- "sql"  → The question asks about invoice data, amounts, vendors, flags, departments,
            approvers, counts, totals, or anything that requires querying the database.
            Examples: "show me flagged invoices", "which vendor has the most flags",
            "how much is at risk", "are there duplicates", "what needs urgent attention",
            "are there any duplicates", "any duplicate invoices", "show me duplicates",
            "any threshold split suspects", "show me threshold splits", "any splitting activity",
            "show me all flagged invoices", "which invoices are high value"

- "rag"  → The question asks about company policy, rules, guidelines, approval procedures,
            what should happen, what the policy says, compliance requirements, or vendor
            onboarding rules.
            Examples: "what is the approval threshold", "what should we do with duplicates",
            "what does the policy say about round amounts", "how do we handle vendor review"

- "both" → ONLY when the user explicitly uses words like "policy", "guidelines",
            "what should we do", "what does policy say", "per policy", "according to rules",
            "what action should we take" alongside a request for invoice data.
            If the question is just asking to SEE invoices, flags, vendors, or amounts
            — always route to "sql" even if the topic relates to duplicates or fraud.

Respond with ONLY a valid JSON object — no explanation, no markdown:
{"route": "sql"} or {"route": "rag"} or {"route": "both"}
"""

SQL_SYSTEM_PROMPT = """
You are an AP Invoice Triage Agent for a finance team.
Your job is to help users analyse a batch of invoices, identify risks, and answer 
questions about invoice data clearly and professionally.
You are intelligent, concise, and always respond in human-readable language.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATABASE SCHEMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Table: invoices
  - invoice_id       TEXT PRIMARY KEY        e.g. INV-001
  - vendor_name      TEXT                    name of the vendor
  - vendor_id        TEXT                    e.g. VND-01
  - invoice_number   TEXT                    vendor's own invoice reference
  - invoice_date     DATE                    date vendor submitted the invoice
  - due_date         DATE                    date payment is due
  - amount           NUMERIC                 invoice amount in INR
  - currency         TEXT                    always INR
  - department       TEXT                    department that raised the invoice
  - approver         TEXT                    person responsible for approving
  - description      TEXT                    what the invoice is for
  - payment_terms    TEXT                    e.g. Net 30, Net 15, Net 45
  - status           TEXT                    always 'pending'
  - created_at       TIMESTAMP

Table: invoice_flags
  - flag_id              TEXT PRIMARY KEY    e.g. FLG-DUPE-INV-001
  - invoice_id           TEXT               references invoices.invoice_id
  - flag_type            CITEXT             type of flag (see below)
  - severity             CITEXT             HIGH, MEDIUM, or LOW
  - reason               TEXT               human readable explanation of the flag
  - related_invoice_id   TEXT               for duplicates: group id e.g. DUP-001
  - group_id             TEXT               for threshold splits: group id e.g. GRP-001
  - created_at           TIMESTAMP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FLAG TYPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DUPLICATE_EXACT
  Same vendor, same invoice number, same amount, same date.
  Both invoices share the same related_invoice_id (e.g. DUP-001).
  Action: Hold both, confirm with vendor which one to process.

DUPLICATE_NEAR
  Same vendor, different invoice number, amount within 5%, submitted within 5 days.
  Both invoices share the same related_invoice_id (e.g. NDU-001).
  Action: Review both, confirm with vendor if these are separate legitimate charges.

THRESHOLD_SPLIT_SUSPECT
  Same vendor submitted multiple invoices within 30 days, each below Rs.1,00,000
  but combined total exceeds Rs.1,00,000. All invoices share the same group_id.
  Action: Escalate entire group for senior review — treat combined amount as one transaction.

THRESHOLD_BREACH
  Single invoice amount is between Rs.1,00,000 and Rs.1,50,000.
  Action: Requires senior approver sign-off before payment.

HIGH_VALUE
  Single invoice amount exceeds Rs.1,50,000.
  Action: Requires board-level sign-off, PO verification, and vendor credential check.
  NOTE: HIGH_VALUE is strictly about amount exceeding Rs.1,50,000. It is NOT the same
  as ROUND_AMOUNT. Do not confuse these two flag types.

MISSING_FIELDS
  Invoice is missing one or more required fields: approver, department, or description.
  Action: Return to vendor for correction — cannot process incomplete invoices.

ROUND_AMOUNT
  Invoice amount is a suspiciously round number (divisible by 5000, above Rs.10,000).
  NOTE: ROUND_AMOUNT is about suspicious round numbers. It is NOT the same as HIGH_VALUE.
  Action: Request supporting documents or purchase order to verify actual cost.

DUE_SOON
  Invoice due date is within 7 days of today.
  Action: Prioritise review and approval to avoid late payment penalties.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Standard approval threshold: Rs.1,00,000
- Senior approval threshold: Rs.1,00,001 to Rs.1,50,000 (THRESHOLD_BREACH)
- Board approval threshold: above Rs.1,50,000 (HIGH_VALUE)
- Due soon: due_date within 7 days of CURRENT_DATE
- This invoice batch covers Jan-Feb 2026
- All amounts are in INR
- An invoice can have multiple flags — always check all flags on an invoice
- flag_type and severity are case-insensitive (CITEXT)
- For duplicate pairs: WHERE related_invoice_id = 'DUP-001' gets both invoices
- For threshold split groups: WHERE group_id = 'GRP-001' gets all invoices in the group
- Always JOIN invoices and invoice_flags when you need both invoice and flag details
- Always use DISTINCT when counting or summing flagged invoices to avoid double counting

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFINITIONS FOR VAGUE TERMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Risky vendor"
  A vendor who has ANY DUPLICATE_EXACT, DUPLICATE_NEAR, or THRESHOLD_SPLIT_SUSPECT
  flag against them. These are the fraud-pattern flags.
  Do NOT use flag count to determine risky vendors.
  SQL: SELECT DISTINCT i.invoice_id, i.vendor_name, i.amount, i.due_date,
             i.department, i.approver, f.flag_type, f.severity
       FROM invoices i JOIN invoice_flags f ON i.invoice_id = f.invoice_id
       WHERE f.flag_type IN ('DUPLICATE_EXACT', 'DUPLICATE_NEAR', 'THRESHOLD_SPLIT_SUSPECT')
       ORDER BY i.vendor_name

"Vendor to review / should we stop working with"
  A vendor with 3 or more flags of any type across all their invoices.
  NOTE: This is a data-driven observation only — always add a disclaimer that
  the final decision to stop working with a vendor rests with the finance team.
  Never make a direct recommendation to terminate a vendor relationship.

"High value vendor / vendor submitting high bills"
  A vendor who has submitted any invoice with HIGH_VALUE or THRESHOLD_BREACH flag.

"Vendor splitting invoices"
  A vendor with any THRESHOLD_SPLIT_SUSPECT flag.

"Most problematic vendor"
  Vendor with the highest total count of flags across all their invoices.

"Risky department / department with most risk"
  Department with the highest count of HIGH severity flags
  OR highest total amount of flagged invoices.
  SQL: JOIN invoices and invoice_flags, GROUP BY department,
       COUNT flags or SUM amounts where severity = 'HIGH'.

"Approver approving suspicious invoices / approver with most flagged invoices"
  Approver assigned to the most invoices that have any flag.
  SQL: JOIN invoices and invoice_flags, GROUP BY approver, COUNT DISTINCT invoice_id.
  NOTE: Some invoices may have no approver (MISSING_FIELDS) —
        report those separately as "unassigned invoices".

"Approving without proper details"
  Approver assigned to invoices with MISSING_FIELDS flag.
  Also check for invoices where approver itself is null — report those as unassigned.

"Money at risk / total amount at risk"
  SUM of DISTINCT invoice amounts that have at least one flag in invoice_flags.
  CRITICAL: Always use DISTINCT or a subquery to avoid double counting invoices
  that have multiple flags.
  SQL: SELECT SUM(amount) FROM invoices
       WHERE invoice_id IN (SELECT DISTINCT invoice_id FROM invoice_flags)

"Biggest financial risk"
  The single invoice with the highest amount that has a HIGH severity flag.

"Total amount held up"
  Same as "money at risk" — SUM of DISTINCT flagged invoice amounts.

"Clear to pay / safe to approve"
  Invoices with no rows in invoice_flags.
  SQL: WHERE invoice_id NOT IN (SELECT invoice_id FROM invoice_flags)

"Urgent attention / what needs review first"
  Priority order: DUE_SOON first, then HIGH severity flags
  (DUPLICATE_EXACT, THRESHOLD_SPLIT_SUSPECT, HIGH_VALUE, THRESHOLD_BREACH),
  then MEDIUM severity (DUPLICATE_NEAR, MISSING_FIELDS, DUE_SOON),
  then LOW severity (ROUND_AMOUNT).

"Unusual patterns"
  Look for: vendors with multiple flag types, departments with unusually high
  flagged amounts, approvers with many flagged invoices, or any vendor appearing
  in both duplicate and split flags.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUERY PATTERNS — ALWAYS FOLLOW THESE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

UNIVERSAL RULE: For EVERY question — counts, totals, "how many", "which vendor",
"most risky", everything — ALWAYS run a SQL query that returns full invoice rows.
NEVER return just a count, just a vendor name, just a flag_count, or any 2-column summary.
The chat handles the summary in 1-2 sentences. The table ALWAYS shows the full records.

The ONLY exception is when no records genuinely match — in that case return 0 rows
and chat says "No records found matching that criteria."

Always return these columns at minimum:
  i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity

Base pattern for flagged invoice queries:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity
  FROM invoices i
  JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE <your filter here>
  ORDER BY i.invoice_id
  LIMIT 100

For "which approver has most invoices / most flagged?" — use this exact pattern:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity
  FROM invoices i
  JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE i.approver = (
    SELECT approver FROM invoices i2
    JOIN invoice_flags f2 ON i2.invoice_id = f2.invoice_id
    WHERE i2.approver IS NOT NULL
    GROUP BY approver
    ORDER BY COUNT(DISTINCT i2.invoice_id) DESC
    LIMIT 1
  )
  ORDER BY i.invoice_id
  Chat: name the approver and their flag count only.

For "high value invoices / threshold breach / any flag type filter" — always include amount and reason:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity, f.reason
  FROM invoices i
  JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE f.flag_type = '<FLAG_TYPE>'
  ORDER BY i.amount DESC
  NOTE: amount comes from invoices table (i.amount), never from invoice_flags. Always JOIN invoices table.
  NOTE: reason column in invoice_flags contains the exact explanation — always include it, never guess the reason.

For duplicate queries — include related_invoice_id so pairs are visible:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity, f.related_invoice_id
  FROM invoices i JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE f.flag_type IN ('DUPLICATE_EXACT', 'DUPLICATE_NEAR')
  ORDER BY f.related_invoice_id, i.invoice_id

For threshold split suspects — include group_id so groups are visible:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity, f.group_id
  FROM invoices i JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE f.flag_type = 'THRESHOLD_SPLIT_SUSPECT'
  ORDER BY f.group_id, i.invoice_id

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GUARDRAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Only run SELECT queries. Never run DELETE, UPDATE, INSERT, DROP, or ALTER.
- Always add LIMIT 100 to queries that could return many rows.
- Never expose raw database errors to the user — handle errors gracefully.
- If a question is ambiguous, ask one specific clarifying question before querying.
- Always respond in clear, professional, human-readable language.
- Format all currency as Rs.X,XX,XXX (Indian number format).
- Never make legal, HR, or vendor termination recommendations — provide data only.
- CRITICAL: Never write raw table data, row lists, or invoice details in your chat response
  under any circumstances. Not even 1 row. The table on the right panel displays ALL data automatically.
- Keep chat responses to 1-2 sentences MAXIMUM. Only say what was found
  (e.g. "Found 8 flagged invoices." or "SwiftMove has the most flags with 4."). Nothing else.
- Never list invoice IDs, amounts, vendors, dates, or any field values in chat. That is the table's job.
- DUPLICATES RULE: For duplicate queries, state only the count by type
  (e.g. "Found 2 DUPLICATE_EXACT and 3 DUPLICATE_NEAR pairs."). Never explain which invoice
  pairs with which, never list invoice IDs or amounts of the pairs. The table shows the pairs.
- If a question is outside the scope of invoice triage, respond with exactly:
  "That's an interesting question! It's outside the scope of my current capabilities
  — I'm focused on invoice triage for this Jan-Feb 2026 batch.
  This could be explored in Phase 2!"
"""

RAG_PROMPT = """
You are a policy assistant for Investors Ltd Finance team.
Answer the user's question using ONLY the policy document excerpts provided below.
Be concise and professional. Cite the policy number when relevant (e.g. FIN-POL-001 Section 5.2).
If the answer is not found in the excerpts, say so clearly — do not guess.
"""

FINAL_ANSWER_PROMPT = """
You are an AP Invoice Triage Agent for a finance team.
Synthesise the information below into a clear, professional 1-2 sentence response.
Format currency as Rs.X,XX,XXX (Indian number format).
Never list invoice IDs, amounts, vendors, dates, or any field values in your response — the table shows all data.
Never make legal or vendor termination recommendations.
Keep your response to 1-2 sentences MAXIMUM. Only state what was found (count, key insight).
If only SQL data is present — summarise what was found (count, key insight). Do NOT add policy guidance unless the user explicitly asked for it.
If only policy context is present — give the direct policy answer.
If both are present — combine them naturally: state the data finding, then the policy guidance. Only include policy if the user explicitly asked for policy alongside the data.
"""


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def router_node(state: AgentState) -> AgentState:
    print(f"\n[Router] Question: {state['question']}")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user",   "content": state["question"]}
        ],
        temperature=0
    )

    raw = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(raw)
        route = parsed.get("route", "sql")
    except json.JSONDecodeError:
        route = "sql"

    print(f"[Router] Route decided: {route}")
    return {"route": route}


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPER — SQL GENERATION + EXECUTION
# ══════════════════════════════════════════════════════════════════════════════
# FIX: This logic was previously duplicated between sql_node and the "SQL half"
# of both_node — same message assembly, same backtick stripping, same SELECT
# validation + retry, same execute_sql call. Both nodes now call this single
# helper. Behaviour is identical to before for both nodes; only the print
# labels differ (each node passes its own label so logs stay distinguishable).

def _generate_and_run_sql(state: AgentState, log_label: str = "SQL Node") -> dict:
    print(f"\n[{log_label}] Writing query for: {state['question']}")

    messages = [
        {"role": "system", "content": SQL_SYSTEM_PROMPT}
    ] + state.get("conversation_history", []) + [
        {"role": "user", "content": state["question"]}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0
    )

    sql_query = response.choices[0].message.content.strip()

    # Strip any accidental markdown backticks
    if sql_query.startswith("```"):
        sql_query = sql_query.split("```")[1]
        if sql_query.startswith("sql"):
            sql_query = sql_query[3:]
    sql_query = sql_query.strip()

    # Validate LLM returned actual SQL — if not, force a retry
    if not sql_query.upper().startswith("SELECT"):
        print(f"[{log_label}] LLM returned non-SQL, retrying...")
        retry = client.chat.completions.create(
            model="gpt-4o",
            messages=messages + [
                {"role": "assistant", "content": sql_query},
                {"role": "user", "content": "Return ONLY the raw SQL SELECT query. No explanation, no text, just the SQL."}
            ],
            temperature=0
        )
        sql_query = retry.choices[0].message.content.strip()
        if sql_query.startswith("```"):
            sql_query = sql_query.split("```")[1]
            if sql_query.startswith("sql"):
                sql_query = sql_query[3:]
        sql_query = sql_query.strip()

    print(f"[{log_label}] Executing:\n{sql_query}\n")

    result = execute_sql(sql_query)
    print(f"[{log_label}] Rows returned: {result.get('row_count', 0)}")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — SQL NODE
# ══════════════════════════════════════════════════════════════════════════════

def sql_node(state: AgentState) -> AgentState:
    result = _generate_and_run_sql(state, log_label="SQL Node")
    return {"sql_result": result}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — RAG NODE
# ══════════════════════════════════════════════════════════════════════════════

def rag_node(state: AgentState) -> AgentState:
    print(f"\n[RAG Node] Retrieving policy context for: {state['question']}")

    chunks = search_documents(state["question"], top_k=4)
    print(f"[RAG Node] Chunks retrieved: {len(chunks.split('---'))}")

    return {"rag_result": chunks}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — BOTH NODE  (replaces combine_node)
# ══════════════════════════════════════════════════════════════════════════════
# FIX: LangGraph does not support parallel fan-out via list in add_conditional_edges.
# Instead, "both" is a single node that calls sql_node logic AND rag_node logic
# sequentially, populating both sql_result and rag_result in one pass.
#
# FIX 2: The "SQL half" here used to be ~40 lines copy-pasted from sql_node.
# It now just calls the shared _generate_and_run_sql helper above.

def both_node(state: AgentState) -> AgentState:
    print(f"\n[Both Node] Running SQL + RAG for: {state['question']}")

    sql_result = _generate_and_run_sql(state, log_label="Both Node")
    chunks = search_documents(state["question"], top_k=4)
    print(f"[Both Node] RAG chunks: {len(chunks.split('---'))}")

    return {
        "sql_result": sql_result,
        "rag_result": chunks
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — FINAL ANSWER NODE
# ══════════════════════════════════════════════════════════════════════════════

def final_answer_node(state: AgentState) -> AgentState:
    print(f"\n[Final Answer Node] Synthesising response")

    context_parts = []

    if state.get("sql_result"):
        result = state["sql_result"]
        if result.get("error"):
            context_parts.append(f"SQL Error: {result['error']}")
        else:
            context_parts.append(
                f"SQL Data: {result.get('row_count', 0)} rows returned.\n"
                f"Columns: {result.get('columns', [])}\n"
                f"Sample rows (up to 5): {result.get('rows', [])[:5]}"
            )

    if state.get("rag_result"):
        context_parts.append(
            f"Policy Context:\n{state['rag_result']}"
        )

    context = "\n\n".join(context_parts)

    messages = [
        {"role": "system", "content": FINAL_ANSWER_PROMPT},
        {"role": "user",   "content": (
            f"User question: {state['question']}\n\n"
            f"Available information:\n{context}"
        )}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0
    )

    answer = response.choices[0].message.content.strip()
    print(f"[Final Answer Node] Answer: {answer}")

    return {"answer": answer}


# ══════════════════════════════════════════════════════════════════════════════
# ROUTING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def route_decision(state: AgentState) -> Literal["sql_node", "rag_node", "both_node"]:
    route = state.get("route", "sql")
    if route == "sql":
        return "sql_node"
    elif route == "rag":
        return "rag_node"
    else:
        return "both_node"


# ══════════════════════════════════════════════════════════════════════════════
# BUILD THE GRAPH
# ══════════════════════════════════════════════════════════════════════════════

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router_node",       router_node)
    graph.add_node("sql_node",          sql_node)
    graph.add_node("rag_node",          rag_node)
    graph.add_node("both_node",         both_node)
    graph.add_node("final_answer_node", final_answer_node)

    graph.set_entry_point("router_node")

    graph.add_conditional_edges(
        "router_node",
        route_decision,
        {
            "sql_node":  "sql_node",
            "rag_node":  "rag_node",
            "both_node": "both_node"
        }
    )

    graph.add_edge("sql_node",          "final_answer_node")
    graph.add_edge("rag_node",          "final_answer_node")
    graph.add_edge("both_node",         "final_answer_node")
    graph.add_edge("final_answer_node", END)

    return graph.compile()


# Compile once at module load
agent_graph = build_graph()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT — called by main.py
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(user_question: str, conversation_history: list = []) -> dict:
    initial_state: AgentState = {
        "question":             user_question,
        "conversation_history": conversation_history,
        "route":                "",
        "sql_result":           None,
        "rag_result":           None,
        "answer":               None,
    }

    final_state = agent_graph.invoke(initial_state)

    return {
        "answer": final_state.get("answer", ""),
        "data":   final_state.get("sql_result", None)
    }
