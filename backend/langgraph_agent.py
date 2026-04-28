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

DUPLICATE_EXACT          HIGH     Same vendor, same invoice number, same amount, same date.
DUPLICATE_NEAR           MEDIUM   Same vendor, different invoice number, amount within 5%, within 5 days.
THRESHOLD_SPLIT_SUSPECT  HIGH     Multiple invoices from same vendor within 30 days, each below Rs.1,00,000, combined exceeds Rs.1,00,000.
THRESHOLD_BREACH         HIGH     Single invoice between Rs.1,00,000 and Rs.1,50,000.
HIGH_VALUE               HIGH     Single invoice above Rs.1,50,000.
MISSING_FIELDS           MEDIUM   Missing approver, department, or description.
ROUND_AMOUNT             LOW      Amount is exact multiple of Rs.1,00,000, above Rs.10,000.
DUE_SOON                 MEDIUM   Due date within 7 days of today.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Standard approval threshold: Rs.1,00,000
- Senior approval: Rs.1,00,001 to Rs.1,50,000 (THRESHOLD_BREACH)
- Board approval: above Rs.1,50,000 (HIGH_VALUE)
- Due soon: due_date within 7 days of CURRENT_DATE
- This invoice batch covers Jan-Feb 2026
- All amounts are in INR
- An invoice can have multiple flags — always check all flags
- flag_type and severity are case-insensitive (CITEXT)
- Always JOIN invoices and invoice_flags when you need both tables
- Always use DISTINCT when counting or summing flagged invoices

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFINITIONS FOR VAGUE TERMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Risky vendor"         → vendor with 2+ flagged invoices OR any DUPLICATE_EXACT/NEAR/SPLIT flag
"Most problematic"     → vendor with highest total flag count
"Money at risk"        → SUM of DISTINCT invoice amounts with at least one flag
"Clear to pay"         → invoices with no rows in invoice_flags
"Urgent attention"     → DUE_SOON first, then HIGH severity, then MEDIUM, then LOW

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUERY PATTERNS — ALWAYS FOLLOW THESE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Always return these columns at minimum:
  i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity

Base pattern:
  SELECT i.invoice_id, i.vendor_name, i.amount, i.due_date, i.department, i.approver, f.flag_type, f.severity
  FROM invoices i
  JOIN invoice_flags f ON i.invoice_id = f.invoice_id
  WHERE <filter>
  ORDER BY i.invoice_id
  LIMIT 100

For duplicates — include related_invoice_id.
For threshold splits — include group_id.
For flag type filters — always include f.reason.
amount always comes from invoices table (i.amount), never from invoice_flags.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GUARDRAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Only run SELECT queries. Never DELETE, UPDATE, INSERT, DROP, ALTER.
- Always add LIMIT 100.
- Format currency as Rs.X,XX,XXX (Indian number format).
- Never make legal or vendor termination recommendations.
- Your response here must be ONLY the SQL query — no explanation, no markdown, no backticks.
  Just the raw SQL. It will be executed directly.
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
Never list invoice IDs, amounts, or field values in your response — the table shows all data.
Never make legal or vendor termination recommendations.
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
# NODE 2 — SQL NODE
# ══════════════════════════════════════════════════════════════════════════════

def sql_node(state: AgentState) -> AgentState:
    print(f"\n[SQL Node] Writing query for: {state['question']}")

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
        print(f"[SQL Node] LLM returned non-SQL, retrying...")
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

    print(f"[SQL Node] Executing:\n{sql_query}\n")

    result = execute_sql(sql_query)
    print(f"[SQL Node] Rows returned: {result.get('row_count', 0)}")

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
# This is functionally identical to the intended parallel result — both data
# sources are available for final_answer_node — without broken graph wiring.

def both_node(state: AgentState) -> AgentState:
    print(f"\n[Both Node] Running SQL + RAG for: {state['question']}")

    # ── SQL half ──
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
    if sql_query.startswith("```"):
        sql_query = sql_query.split("```")[1]
        if sql_query.startswith("sql"):
            sql_query = sql_query[3:]
    sql_query = sql_query.strip()

    # Validate LLM returned actual SQL — if not, force a retry
    if not sql_query.upper().startswith("SELECT"):
        print(f"[Both Node] LLM returned non-SQL, retrying...")
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

    print(f"[Both Node] Executing SQL:\n{sql_query}\n")
    sql_result = execute_sql(sql_query)
    print(f"[Both Node] SQL rows: {sql_result.get('row_count', 0)}")

    # ── RAG half ──
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
    graph.add_node("both_node",         both_node)       # FIX: replaces combine_node
    graph.add_node("final_answer_node", final_answer_node)

    graph.set_entry_point("router_node")

    # FIX: route_decision now returns string keys only — no lists
    graph.add_conditional_edges(
        "router_node",
        route_decision,
        {
            "sql_node":  "sql_node",
            "rag_node":  "rag_node",
            "both_node": "both_node"
        }
    )

    # All three paths converge on final_answer_node
    graph.add_edge("sql_node",          "final_answer_node")
    graph.add_edge("rag_node",          "final_answer_node")
    graph.add_edge("both_node",         "final_answer_node")   # FIX: wired correctly
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
