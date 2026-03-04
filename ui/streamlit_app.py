import streamlit as st
import streamlit.components.v1 as components

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AP Triage Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Hide all Streamlit UI chrome ──────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stHeader"] { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
[data-testid="block-container"] { padding: 0 !important; max-width: 100% !important; }
section[data-testid="stMain"] { padding: 0 !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }
iframe { border: none !important; background: #0a0d14 !important; }
</style>
""", unsafe_allow_html=True)

# ── FastAPI URL ───────────────────────────────────────────────────────────────
FASTAPI_URL = "https://ap-invoice-triage.onrender.com"  # 🔁 Replace with your Render URL

# ── Full HTML UI ──────────────────────────────────────────────────────────────
html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0a0d14; --surface: #111520; --surface2: #161c2e;
    --border: #1e2740; --accent: #3b82f6; --accent2: #6366f1;
    --green: #10b981; --red: #ef4444; --orange: #f59e0b;
    --text: #e2e8f0; --text-muted: #64748b; --text-dim: #334155;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'DM Sans', sans-serif;
    background: var(--bg); color: var(--text);
    height: 100vh; display: flex; flex-direction: column; overflow: hidden;
  }}
  header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 24px; height: 52px;
    border-bottom: 1px solid var(--border); background: var(--surface); flex-shrink: 0;
  }}
  .logo {{ display: flex; align-items: center; gap: 10px; }}
  .logo-icon {{
    width: 28px; height: 28px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 14px;
  }}
  .logo-text {{ font-family: 'Syne', sans-serif; font-weight: 700; font-size: 15px; letter-spacing: 0.02em; }}
  .logo-text span {{ color: var(--accent); }}
  .header-right {{ display: flex; align-items: center; gap: 8px; }}
  .status-dot {{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite;
  }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
  .status-text {{ font-size: 11px; color: var(--text-muted); font-family: 'DM Mono', monospace; }}
  .main {{ display: flex; flex: 1; overflow: hidden; }}
  .left-panel {{
    width: 300px; flex-shrink: 0;
    border-right: 1px solid var(--border); background: var(--surface);
    display: flex; flex-direction: column; overflow: hidden;
  }}
  .left-top {{ padding: 16px; border-bottom: 1px solid var(--border); }}
  .load-btn {{
    width: 100%; padding: 10px 16px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: 8px; color: white;
    font-family: 'Syne', sans-serif; font-weight: 600; font-size: 13px;
    letter-spacing: 0.04em; cursor: pointer; transition: all 0.2s;
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }}
  .load-btn:hover {{ opacity: 0.9; transform: translateY(-1px); box-shadow: 0 4px 20px rgba(59,130,246,0.3); }}
  .batch-info {{ margin-top: 12px; padding: 10px 12px; background: var(--surface2); border-radius: 8px; border: 1px solid var(--border); display: none; }}
  .batch-info.visible {{ display: block; }}
  .batch-row {{ display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }}
  .batch-label {{ font-size: 11px; color: var(--text-muted); font-family: 'DM Mono', monospace; }}
  .batch-value {{ font-size: 11px; color: var(--text); font-family: 'DM Mono', monospace; font-weight: 500; }}
  .batch-value.flagged {{ color: var(--orange); }}
  .batch-value.ok {{ color: var(--green); }}
  .chat-area {{ display: flex; flex-direction: column; padding: 12px; gap: 10px; }}
  .chat-messages {{ overflow-y: auto; display: flex; flex-direction: column; gap: 10px; max-height: 220px; }}
  .chat-messages:empty {{ display: none; }}
  .chat-messages::-webkit-scrollbar {{ width: 3px; }}
  .chat-messages::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  .suggestions {{ display: flex; flex-direction: column; gap: 6px; padding-top: 4px; }}
  .suggestion-label {{
    font-size: 10px; color: var(--text-dim); font-family: 'DM Mono', monospace;
    text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 2px;
  }}
  .suggestion-chip {{
    padding: 7px 10px; background: transparent;
    border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-muted); font-size: 11px; cursor: pointer;
    transition: all 0.15s; text-align: left;
  }}
  .suggestion-chip:hover {{ border-color: var(--accent); color: var(--text); background: rgba(59,130,246,0.05); }}
  .msg {{ display: flex; flex-direction: column; gap: 2px; animation: fadeIn 0.3s ease; }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  .msg.user {{ align-items: flex-end; }}
  .msg.agent {{ align-items: flex-start; }}
  .msg-bubble {{ max-width: 85%; padding: 8px 11px; border-radius: 10px; font-size: 12px; line-height: 1.5; }}
  .msg.user .msg-bubble {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); color: white; border-bottom-right-radius: 3px; }}
  .msg.agent .msg-bubble {{ background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-bottom-left-radius: 3px; }}
  .msg-time {{ font-size: 9px; color: var(--text-dim); font-family: 'DM Mono', monospace; padding: 0 4px; }}
  .chat-input-area {{ display: flex; gap: 6px; padding-top: 8px; border-top: 1px solid var(--border); }}
  .chat-input {{
    flex: 1; padding: 8px 12px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 12px;
    font-family: 'DM Sans', sans-serif; outline: none; transition: border-color 0.2s;
  }}
  .chat-input:focus {{ border-color: var(--accent); }}
  .chat-input::placeholder {{ color: var(--text-dim); }}
  .chat-input:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .send-btn {{
    width: 34px; height: 34px; background: var(--accent);
    border: none; border-radius: 8px; color: white;
    cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s;
  }}
  .send-btn:hover {{ background: var(--accent2); }}
  .send-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .right-panel {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; background: var(--bg); }}
  .right-panel-inner {{ flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }}
  .right-panel-inner::-webkit-scrollbar {{ width: 3px; }}
  .right-panel-inner::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  .empty-state {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-dim); }}
  .empty-icon {{ font-size: 36px; opacity: 0.3; }}
  .empty-text {{ font-size: 12px; font-family: 'DM Mono', monospace; text-align: center; line-height: 1.6; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; animation: fadeIn 0.4s ease; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 4px; }}
  .card-label {{ font-size: 10px; color: var(--text-muted); font-family: 'DM Mono', monospace; text-transform: uppercase; letter-spacing: 0.06em; }}
  .card-value {{ font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 700; }}
  .card-value.blue {{ color: var(--accent); }}
  .card-value.orange {{ color: var(--orange); }}
  .card-value.green {{ color: var(--green); }}
  .card-sub {{ font-size: 10px; color: var(--text-muted); }}
  .table-wrap {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; animation: fadeIn 0.4s ease; }}
  .table-header-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border); }}
  .table-title {{ font-size: 11px; font-family: 'Syne', sans-serif; font-weight: 600; color: var(--text); text-transform: uppercase; letter-spacing: 0.06em; }}
  .table-count {{ font-size: 10px; color: var(--text-muted); font-family: 'DM Mono', monospace; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  thead th {{ padding: 8px 12px; text-align: left; font-size: 10px; color: var(--text-muted); font-family: 'DM Mono', monospace; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); background: var(--surface2); }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.15s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: var(--surface2); }}
  tbody td {{ padding: 8px 12px; color: var(--text); font-size: 11px; }}
  .badge {{ display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-family: 'DM Mono', monospace; font-weight: 500; }}
  .badge-red {{ background: rgba(239,68,68,0.15); color: var(--red); }}
  .badge-orange {{ background: rgba(245,158,11,0.15); color: var(--orange); }}
  .badge-blue {{ background: rgba(59,130,246,0.15); color: var(--accent); }}
  .badge-green {{ background: rgba(16,185,129,0.15); color: var(--green); }}
  .badge-purple {{ background: rgba(99,102,241,0.15); color: var(--accent2); }}
  .sev-high {{ color: var(--red); font-weight: 500; }}
  .sev-med {{ color: var(--orange); font-weight: 500; }}
  .sev-low {{ color: var(--green); font-weight: 500; }}
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; animation: fadeIn 0.5s ease; }}
  .chart-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
  .chart-title {{ font-size: 10px; color: var(--text-muted); font-family: 'DM Mono', monospace; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px; }}
  .chart-container {{ position: relative; height: 160px; }}
  .typing {{ display: flex; gap: 3px; padding: 8px 11px; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; border-bottom-left-radius: 3px; width: fit-content; }}
  .typing span {{ width: 5px; height: 5px; background: var(--text-muted); border-radius: 50%; animation: bounce 1.2s infinite; }}
  .typing span:nth-child(2) {{ animation-delay: 0.2s; }}
  .typing span:nth-child(3) {{ animation-delay: 0.4s; }}
  @keyframes bounce {{ 0%, 80%, 100% {{ transform: translateY(0); opacity: 0.4; }} 40% {{ transform: translateY(-4px); opacity: 1; }} }}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">⚡</div>
    <div class="logo-text">AP <span>Triage</span> Agent</div>
  </div>
  <div class="header-right">
    <div class="status-dot"></div>
    <div class="status-text">CONNECTED · SUPABASE</div>
  </div>
</header>
<div class="main">
  <div class="left-panel">
    <div class="left-top">
      <button class="load-btn" onclick="loadBatch()">⬇ Load Invoice Batch</button>
      <div class="batch-info" id="batchInfo">
        <div class="batch-row"><span class="batch-label">PERIOD</span><span class="batch-value" id="bPeriod">—</span></div>
        <div class="batch-row"><span class="batch-label">TOTAL</span><span class="batch-value ok" id="bTotal">—</span></div>
        <div class="batch-row"><span class="batch-label">FLAGGED</span><span class="batch-value flagged" id="bFlagged">—</span></div>
        <div class="batch-row"><span class="batch-label">TOTAL SPEND</span><span class="batch-value" id="bSpend">—</span></div>
      </div>
    </div>
    <div class="chat-area">
      <div class="chat-messages" id="chatMessages"></div>
      <div class="chat-input-area">
        <input class="chat-input" id="chatInput" placeholder="Ask about your invoices..." disabled onkeydown="handleKey(event)">
        <button class="send-btn" id="sendBtn" onclick="sendMessage()" disabled>➤</button>
      </div>
      <div class="suggestions" id="suggestions" style="display:none;">
        <div class="suggestion-label">Try asking</div>
        <div class="suggestion-chip" onclick="sendSuggestion(this)">Show me all flagged invoices</div>
        <div class="suggestion-chip" onclick="sendSuggestion(this)">Are there any duplicates?</div>
        <div class="suggestion-chip" onclick="sendSuggestion(this)">Which invoices are high value?</div>
        <div class="suggestion-chip" onclick="sendSuggestion(this)">Any threshold split suspects?</div>
      </div>
    </div>
  </div>
  <div class="right-panel">
    <div class="right-panel-inner" id="rightPanel">
      <div class="empty-state" id="emptyState">
        <div class="empty-icon">📂</div>
        <div class="empty-text">Click "Load Invoice Batch"<br>to begin triage session</div>
      </div>
    </div>
  </div>
</div>

<script>
const FASTAPI_URL = "{FASTAPI_URL}";
let batchLoaded = false;
let barChart = null;
let pieChart = null;
let conversationHistory = [];

async function loadBatch() {{
  if (batchLoaded) return;
  try {{
    const res = await fetch(FASTAPI_URL + '/load-batch');
    const data = await res.json();
    const info = data.batch_info || {{}};
    document.getElementById('bPeriod').innerText = info.period || '—';
    document.getElementById('bTotal').innerText = (info.total_invoices || '—') + ' invoices';
    document.getElementById('bFlagged').innerText = (info.total_flagged || '—') + ' invoices';
    const spend = info.total_spend ? 'Rs.' + Number(info.total_spend).toLocaleString('en-IN') : '—';
    document.getElementById('bSpend').innerText = spend;
    document.getElementById('batchInfo').classList.add('visible');
    document.getElementById('chatInput').disabled = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('suggestions').style.display = 'flex';
    document.getElementById('suggestions').style.flexDirection = 'column';
    batchLoaded = true;
    addMessage('agent', data.message || 'Invoice batch loaded. Ask me anything about this batch.');
    showDashboard(data);
  }} catch(e) {{
    alert('Could not connect to backend: ' + e.message);
  }}
}}

async function sendMessage() {{
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || !batchLoaded) return;
  document.getElementById('suggestions').style.display = 'none';
  addMessage('user', text);
  input.value = '';
  const typingEl = addTyping();
  try {{
    const res = await fetch(FASTAPI_URL + '/triage', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{question: text, conversation_history: conversationHistory}})
    }});
    const data = await res.json();
    typingEl.remove();
    conversationHistory.push({{role: 'user', content: text}});
    conversationHistory.push({{role: 'assistant', content: data.answer || ''}});
    addMessage('agent', data.answer || '');
    showResult(data);
  }} catch(e) {{
    typingEl.remove();
    addMessage('agent', 'Sorry, could not reach the backend.');
  }}
}}

function sendSuggestion(el) {{
  document.getElementById('chatInput').value = el.innerText;
  sendMessage();
}}

function handleKey(e) {{ if (e.key === 'Enter') sendMessage(); }}

function addMessage(role, text) {{
  const msgs = document.getElementById('chatMessages');
  const now = new Date().toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit'}});
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = '<div class="msg-bubble">' + text + '</div><div class="msg-time">' + now + '</div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}}

function addTyping() {{
  const msgs = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'msg agent';
  div.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}}

function showDashboard(data) {{
  const panel = document.getElementById('rightPanel');
  const info = data.batch_info || {{}};
  const spend = info.total_spend ? 'Rs.' + Number(info.total_spend).toLocaleString('en-IN') : '—';

  // Build flag breakdown table
  const flagRows = (data.flag_breakdown || []).map(r =>
    `<tr><td>${{r.flag_type}}</td><td>${{r.count}}</td></tr>`
  ).join('');

  // Build chart data from backend
  const deptData = data.dept_spend || [];
  const flagData = data.flag_breakdown || [];
  const chartData = {{
    bar: {{
      labels: deptData.map(d => d.department),
      values: deptData.map(d => d.spend)
    }},
    pie: {{
      labels: flagData.map(d => d.flag_type),
      values: flagData.map(d => d.count)
    }}
  }};

  panel.innerHTML = `
    <div class="summary-cards">
      <div class="card"><div class="card-label">Total Invoices</div><div class="card-value blue">${{info.total_invoices||'—'}}</div><div class="card-sub">${{info.period||''}}</div></div>
      <div class="card"><div class="card-label">Flagged</div><div class="card-value orange">${{info.total_flagged||'—'}}</div><div class="card-sub">Need attention</div></div>
      <div class="card"><div class="card-label">Clear</div><div class="card-value green">${{info.clear_invoices||'—'}}</div><div class="card-sub">Ready to process</div></div>
      <div class="card"><div class="card-label">Total Spend</div><div class="card-value blue">${{spend}}</div><div class="card-sub">Across all invoices</div></div>
    </div>
    <div class="table-wrap">
      <div class="table-header-bar">
        <div class="table-title">Flag Breakdown</div>
        <div class="table-count">${{(data.flag_breakdown||[]).length}} flag types</div>
      </div>
      <table>
        <thead><tr><th>Flag Type</th><th>Count</th></tr></thead>
        <tbody>${{flagRows}}</tbody>
      </table>
    </div>
    <div class="charts-row">
      <div class="chart-box"><div class="chart-title">Spend by Department</div><div class="chart-container"><canvas id="barChart"></canvas></div></div>
      <div class="chart-box"><div class="chart-title">Flag Type Breakdown</div><div class="chart-container"><canvas id="pieChart"></canvas></div></div>
    </div>`;
  setTimeout(() => renderCharts(chartData), 100);
}}

function showResult(data) {{
  const panel = document.getElementById('rightPanel');
  const rows_data = (data.data && data.data.rows) ? data.data.rows : [];
  const rows = rows_data.map(r =>
    '<tr>' + Object.values(r).map(v => '<td>' + (v === null ? '—' : v) + '</td>').join('') + '</tr>'
  ).join('');
  const headers = rows_data.length > 0
    ? '<tr>' + Object.keys(rows_data[0]).map(k => '<th>' + k + '</th>').join('') + '</tr>'
    : '';
  let html = '';
  if (rows_data.length > 0) {{
    html += `
      <div class="table-wrap">
        <div class="table-header-bar">
          <div class="table-title">Results</div>
          <div class="table-count">${{rows_data.length}} records</div>
        </div>
        <div style="overflow-x: auto;">
          <table style="width: auto; min-width: 100%; white-space: nowrap;"><thead>${{headers}}</thead><tbody>${{rows}}</tbody></table>
        </div>
      </div>`;
  }}
  panel.innerHTML = html || '<div class="empty-state"><div class="empty-text">No data to display</div></div>';
}}

function renderCharts(chartData) {{
  const barCtx = document.getElementById('barChart');
  const pieCtx = document.getElementById('pieChart');
  if (barCtx && chartData.bar) {{
    if (barChart) barChart.destroy();
    barChart = new Chart(barCtx, {{
      type: 'bar',
      data: {{
        labels: chartData.bar.labels,
        datasets: [{{ data: chartData.bar.values, backgroundColor: ['#3b82f6','#6366f1','#f59e0b','#10b981','#ef4444'], borderRadius: 4, borderSkipped: false }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b', font: {{ size: 9 }} }}, grid: {{ color: '#1e2740' }} }},
          y: {{ ticks: {{ color: '#64748b', font: {{ size: 9 }} }}, grid: {{ color: '#1e2740' }} }}
        }}
      }}
    }});
  }}
  if (pieCtx && chartData.pie) {{
    if (pieChart) pieChart.destroy();
    pieChart = new Chart(pieCtx, {{
      type: 'doughnut',
      data: {{
        labels: chartData.pie.labels,
        datasets: [{{ data: chartData.pie.values, backgroundColor: ['#f59e0b','#ef4444','#6366f1','#3b82f6','#10b981'], borderWidth: 0 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'right', labels: {{ color: '#64748b', font: {{ size: 9 }}, boxWidth: 10, padding: 8 }} }} }}
      }}
    }});
  }}
}}
</script>
</body>
</html>
"""

components.html(html, height=800, scrolling=False)
