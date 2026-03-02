import streamlit as st
import requests
import pandas as pd

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AP Triage Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── FastAPI URL ───────────────────────────────────────────────────────────────
FASTAPI_URL = "https://your-app.onrender.com"  # 🔁 Replace with your Render URL

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
"""<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">""",
unsafe_allow_html=True
)
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0a0d14 !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }
[data-testid="stAppViewContainer"] > section > div { padding-top: 0 !important; }
[data-testid="block-container"] { padding: 0 !important; max-width: 100% !important; }

/* Header */
.ap-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 24px; height: 52px;
    border-bottom: 1px solid #1e2740; background: #111520;
    position: sticky; top: 0; z-index: 100;
}
.ap-logo { display: flex; align-items: center; gap: 10px; }
.ap-logo-icon {
    width: 28px; height: 28px;
    background: linear-gradient(135deg, #3b82f6, #6366f1);
    border-radius: 6px; display: flex; align-items: center;
    justify-content: center; font-size: 14px;
}
.ap-logo-text { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 15px; color: #e2e8f0; }
.ap-logo-text span { color: #3b82f6; }
.ap-status { display: flex; align-items: center; gap: 8px; }
.ap-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #10b981; box-shadow: 0 0 6px #10b981;
    display: inline-block; animation: pulse 2s infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.ap-status-text { font-size: 11px; color: #64748b; font-family: 'DM Mono', monospace; }

/* Load button */
.stButton > button {
    width: 100% !important;
    background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important; padding: 10px 16px !important;
    font-family: 'Syne', sans-serif !important; font-weight: 600 !important;
    font-size: 13px !important; letter-spacing: 0.04em !important;
}
.stButton > button:hover { opacity: 0.9 !important; box-shadow: 0 4px 20px rgba(59,130,246,0.3) !important; }

/* Batch info */
.batch-info-box {
    margin-top: 12px; padding: 10px 12px;
    background: #161c2e; border-radius: 8px; border: 1px solid #1e2740;
}
.batch-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }
.batch-label { font-size: 11px; color: #64748b; font-family: 'DM Mono', monospace; }
.batch-val { font-size: 11px; font-family: 'DM Mono', monospace; font-weight: 500; color: #e2e8f0; }
.batch-val-green { font-size: 11px; font-family: 'DM Mono', monospace; font-weight: 500; color: #10b981; }
.batch-val-orange { font-size: 11px; font-family: 'DM Mono', monospace; font-weight: 500; color: #f59e0b; }

/* Chat bubbles */
.chat-msg-user { display: flex; justify-content: flex-end; margin: 4px 0; }
.chat-msg-agent { display: flex; justify-content: flex-start; margin: 4px 0; }
.bubble-user {
    background: linear-gradient(135deg, #3b82f6, #6366f1);
    color: white; padding: 8px 12px;
    border-radius: 10px 10px 3px 10px;
    font-size: 12px; line-height: 1.5; max-width: 85%;
}
.bubble-agent {
    background: #161c2e; border: 1px solid #1e2740;
    color: #e2e8f0; padding: 8px 12px;
    border-radius: 10px 10px 10px 3px;
    font-size: 12px; line-height: 1.5; max-width: 85%;
}

/* Suggestion chips */
.suggest-label {
    font-size: 10px; color: #334155; font-family: 'DM Mono', monospace;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-bottom: 4px; margin-top: 8px;
}

/* Summary cards */
.cards-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
.card { background: #111520; border: 1px solid #1e2740; border-radius: 10px; padding: 12px; }
.card-label { font-size: 10px; color: #64748b; font-family: 'DM Mono', monospace; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
.card-val-blue { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 700; color: #3b82f6; }
.card-val-orange { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 700; color: #f59e0b; }
.card-val-green { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 700; color: #10b981; }
.card-sub { font-size: 10px; color: #64748b; margin-top: 2px; }

/* Table */
.table-wrap { background: #111520; border: 1px solid #1e2740; border-radius: 10px; overflow: hidden; margin-bottom: 14px; }
.table-header-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #1e2740; }
.table-title { font-size: 11px; font-family: 'Syne', sans-serif; font-weight: 600; color: #e2e8f0; text-transform: uppercase; letter-spacing: 0.06em; }
.table-count { font-size: 10px; color: #64748b; font-family: 'DM Mono', monospace; }

/* Empty state */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh; gap: 10px; color: #334155; }
.empty-icon { font-size: 36px; opacity: 0.3; }
.empty-text { font-size: 12px; font-family: 'DM Mono', monospace; text-align: center; line-height: 1.6; }

::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1e2740; border-radius: 3px; }
[data-testid="column"] { padding: 0 !important; }
</style>""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "batch_loaded" not in st.session_state:
    st.session_state.batch_loaded = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "right_panel_view" not in st.session_state:
    st.session_state.right_panel_view = "empty"
if "batch_info" not in st.session_state:
    st.session_state.batch_info = {}
if "table_data" not in st.session_state:
    st.session_state.table_data = None
if "chart_data" not in st.session_state:
    st.session_state.chart_data = None
if "suggestions_hidden" not in st.session_state:
    st.session_state.suggestions_hidden = False

# ── API call functions ────────────────────────────────────────────────────────
def api_load_batch():
    """Call FastAPI to load batch info — returns summary stats"""
    try:
        response = requests.get(f"{FASTAPI_URL}/load-batch")
        return response.json()
    except Exception as e:
        st.error(f"Could not connect to backend: {e}")
        return None

def api_ask(question):
    """Send user question to FastAPI agent — returns agent answer + table data + chart data"""
    try:
        response = requests.post(f"{FASTAPI_URL}/triage", json={"question": question})
        return response.json()
    except Exception as e:
        st.error(f"Could not connect to backend: {e}")
        return None

# ── Render helpers ─────────────────────────────────────────────────────────────
def render_header():
    st.markdown("""
    <div class="ap-header">
        <div class="ap-logo">
            <div class="ap-logo-icon">⚡</div>
            <div class="ap-logo-text">AP <span>Triage</span> Agent</div>
        </div>
        <div class="ap-status">
            <span class="ap-dot"></span>
            <span class="ap-status-text">CONNECTED · SUPABASE</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_summary_cards(info):
    """info = dict with keys: total, flagged, clear, spend, period"""
    st.markdown(f"""
    <div class="cards-row">
        <div class="card">
            <div class="card-label">Total Invoices</div>
            <div class="card-val-blue">{info.get('total', '—')}</div>
            <div class="card-sub">{info.get('period', '')}</div>
        </div>
        <div class="card">
            <div class="card-label">Flagged</div>
            <div class="card-val-orange">{info.get('flagged', '—')}</div>
            <div class="card-sub">Need attention</div>
        </div>
        <div class="card">
            <div class="card-label">Clear</div>
            <div class="card-val-green">{info.get('clear', '—')}</div>
            <div class="card-sub">Ready to process</div>
        </div>
        <div class="card">
            <div class="card-label">Total Spend</div>
            <div class="card-val-blue">{info.get('spend', '—')}</div>
            <div class="card-sub">Across all invoices</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_table(title, df):
    """Render a titled table with dataframe"""
    if df is None or len(df) == 0:
        return
    st.markdown(f"""
    <div class="table-wrap">
        <div class="table-header-bar">
            <div class="table-title">{title}</div>
            <div class="table-count">{len(df)} records</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True, height=min(35 * len(df) + 38, 350))

def render_charts(chart_data):
    """
    chart_data = {
        "bar": {"labels": [...], "values": [...], "title": "..."},
        "pie": {"labels": [...], "values": [...], "title": "..."}
    }
    Only renders if chart_data is provided.
    """
    if not chart_data:
        return

    import plotly.graph_objects as go

    col1, col2 = st.columns(2)

    if "bar" in chart_data:
        with col1:
            bar = chart_data["bar"]
            fig = go.Figure(go.Bar(
                x=bar["labels"], y=bar["values"],
                marker_color=['#3b82f6','#6366f1','#f59e0b','#10b981','#ef4444'],
                marker=dict(line=dict(width=0)),
            ))
            fig.update_layout(
                title=dict(text=bar.get("title",""), font=dict(size=11, color='#64748b', family='DM Mono')),
                paper_bgcolor='#111520', plot_bgcolor='#111520',
                margin=dict(l=10, r=10, t=35, b=10), height=200,
                xaxis=dict(tickfont=dict(size=9, color='#64748b'), gridcolor='#1e2740', showgrid=False),
                yaxis=dict(tickfont=dict(size=9, color='#64748b'), gridcolor='#1e2740'),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    if "pie" in chart_data:
        with col2:
            pie = chart_data["pie"]
            fig = go.Figure(go.Pie(
                labels=pie["labels"], values=pie["values"],
                marker_colors=['#f59e0b','#ef4444','#6366f1','#3b82f6','#10b981'],
                hole=0.55, textinfo='none',
            ))
            fig.update_layout(
                title=dict(text=pie.get("title",""), font=dict(size=11, color='#64748b', family='DM Mono')),
                paper_bgcolor='#111520', plot_bgcolor='#111520',
                margin=dict(l=10, r=10, t=35, b=10), height=200,
                legend=dict(font=dict(size=9, color='#64748b'), orientation='v', x=0.7),
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ── RENDER ─────────────────────────────────────────────────────────────────────
render_header()

left_col, right_col = st.columns([1, 2.8], gap="small")

# ── LEFT PANEL ────────────────────────────────────────────────────────────────
with left_col:
    st.markdown('<div style="background:#111520; border-right:1px solid #1e2740; padding:16px; min-height:100vh;">', unsafe_allow_html=True)
    
    # Load button
    if st.button("⬇  Load Invoice Batch"):
        with st.spinner("Loading..."):
            result = api_load_batch()
            if result:
                st.session_state.batch_loaded = True
                st.session_state.batch_info = result.get("batch_info", {})
                st.session_state.table_data = result.get("table_data")
                st.session_state.chart_data = result.get("chart_data")
                st.session_state.right_panel_view = "all"
                st.session_state.messages = [{
                    "role": "agent",
                    "text": result.get("message", "Invoice batch loaded. Ask me anything.")
                }]

    # Batch info
    if st.session_state.batch_loaded and st.session_state.batch_info:
        info = st.session_state.batch_info
        st.markdown(f"""
        <div class="batch-info-box">
            <div class="batch-row"><span class="batch-label">PERIOD</span><span class="batch-val">{info.get('period','—')}</span></div>
            <div class="batch-row"><span class="batch-label">TOTAL</span><span class="batch-val-green">{info.get('total','—')} invoices</span></div>
            <div class="batch-row"><span class="batch-label">FLAGGED</span><span class="batch-val-orange">{info.get('flagged','—')} invoices</span></div>
            <div class="batch-row"><span class="batch-label">TOTAL SPEND</span><span class="batch-val">{info.get('spend','—')}</span></div>
        </div>
        """, unsafe_allow_html=True)

    # Chat messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-msg-user"><div class="bubble-user">{msg["text"]}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-msg-agent"><div class="bubble-agent">{msg["text"]}</div></div>', unsafe_allow_html=True)

    # Suggestions + chat input
    if st.session_state.batch_loaded:
        if not st.session_state.suggestions_hidden:
            st.markdown('<div class="suggest-label">Try asking</div>', unsafe_allow_html=True)
            for s in [
                "Show me all flagged invoices",
                "Are there any duplicates?",
                "Which invoices are high value?",
                "Any threshold split suspects?"
            ]:
                if st.button(s, key=f"sug_{s}"):
                    st.session_state.suggestions_hidden = True
                    st.session_state.messages.append({"role": "user", "text": s})
                    with st.spinner("Thinking..."):
                        result = api_ask(s)
                    if result:
                        st.session_state.messages.append({"role": "agent", "text": result.get("answer", "")})
                        st.session_state.table_data = result.get("table_data")
                        st.session_state.chart_data = result.get("chart_data")
                        st.session_state.right_panel_view = "result"
                    st.rerun()

        user_input = st.chat_input("Ask about your invoices...")
        if user_input:
            st.session_state.suggestions_hidden = True
            st.session_state.messages.append({"role": "user", "text": user_input})
            with st.spinner("Thinking..."):
                result = api_ask(user_input)
            if result:
                st.session_state.messages.append({"role": "agent", "text": result.get("answer", "")})
                st.session_state.table_data = result.get("table_data")
                st.session_state.chart_data = result.get("chart_data")
                st.session_state.right_panel_view = "result"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ── RIGHT PANEL ───────────────────────────────────────────────────────────────
with right_col:

    view = st.session_state.right_panel_view

    if view == "empty":
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📂</div>
            <div class="empty-text">Click "Load Invoice Batch"<br>to begin triage session</div>
        </div>
        """, unsafe_allow_html=True)

    elif view == "all":
        # On load — show summary cards + full invoice table + charts
        if st.session_state.batch_info:
            render_summary_cards(st.session_state.batch_info)
        if st.session_state.table_data is not None:
            render_table("All Invoices", pd.DataFrame(st.session_state.table_data))
        if st.session_state.chart_data:
            render_charts(st.session_state.chart_data)

    elif view == "result":
        # After a chat question — show table + charts returned by agent
        if st.session_state.table_data is not None:
            render_table("Results", pd.DataFrame(st.session_state.table_data))
        if st.session_state.chart_data:
            render_charts(st.session_state.chart_data)
