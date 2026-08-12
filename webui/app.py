"""CodeGuard WebUI — Flask-based web interface with real Agent integration.

Provides browser-based access to the CodeGuard agent with:
- Background agent execution via threading
- Real-time log streaming via status polling
- Interactive approval modal for HIGH-risk actions
"""

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template_string, request

from src.agent import Agent
from src.llm_client import RealLLM
from src.models import ApprovalResult

app = Flask(__name__)

# ---------------------------------------------------------------------------
# shared session state
# ---------------------------------------------------------------------------

_sessions = {}          # session_id → state dict
_sessions_lock = threading.Lock()


def _json_friendly(obj):
    """Convert any object into a JSON-serializable form."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): _json_friendly(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_friendly(i) for i in obj]
    return str(obj)


def _create_session(task: str, workspace: str) -> str:
    """Create a new agent session running in a background thread."""
    session_id = uuid.uuid4().hex[:8]
    state = {
        "session_id": session_id,
        "task": task,
        "workspace": workspace,
        "status": "running",
        "logs": [],
        "finish_reason": None,
        "stop_reason": None,
        "error": None,
        "steps": 0,
        # approval
        "waiting_for_approval": False,
        "pending_action": None,
        "approval_event": threading.Event(),
        "approval_decision": None,
    }

    def progress_callback(event_type: str, data: dict):
        """Called by Agent at each significant event."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": _json_friendly(data),
        }
        with _sessions_lock:
            state["logs"].append(entry)
            if "step" in data:
                state["steps"] = max(state["steps"], data["step"])
            if event_type == "completed":
                state["status"] = "completed"
                state["finish_reason"] = data.get("finish_reason")
                state["stop_reason"] = data.get("stop_reason")
            elif event_type == "error":
                state["status"] = "error"
                state["error"] = str(data.get("error", ""))

    def web_approval_fn(risk):
        """Custom approval function — blocks until web UI provides decision."""
        action = risk.action if risk.action else {}
        content = (action.get("content") or "")
        with _sessions_lock:
            state["waiting_for_approval"] = True
            state["pending_action"] = {
                "action": action.get("action", "unknown"),
                "path": action.get("path", ""),
                "command": action.get("command", ""),
                "content_preview": content[:200] if content else "",
                "risk_level": risk.level.value if hasattr(risk.level, "value") else str(risk.level),
                "rule": risk.rule,
            }
            state["approval_event"].clear()

        # notify frontend that we're waiting
        progress_callback("awaiting_approval", {
            "action": state["pending_action"],
        })

        # block until /approve or /reject is called
        state["approval_event"].wait()

        with _sessions_lock:
            state["waiting_for_approval"] = False
            approved = bool(state["approval_decision"])
            state["pending_action"] = None
            state["approval_decision"] = None

        return ApprovalResult(
            approved=approved,
            reason="APPROVED" if approved else "REJECTED",
        )

    agent = Agent(
        llm_client=RealLLM(),
        progress_callback=progress_callback,
        approval_fn=web_approval_fn,
    )

    def _run():
        try:
            agent.run(task=task, workspace=workspace)
        except Exception as exc:
            progress_callback("error", {"error": str(exc)})

    thread = threading.Thread(target=_run, daemon=True)
    state["thread"] = thread
    thread.start()

    with _sessions_lock:
        _sessions[session_id] = state
    return session_id


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(INDEX_TEMPLATE)


@app.route("/run", methods=["POST"])
def run_task():
    task = request.form.get("task", "")
    if not task:
        return jsonify({"success": False, "error": "No task provided"}), 400

    workspace = tempfile.mkdtemp(prefix="codeguard_ws_")
    try:
        session_id = _create_session(task, workspace)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({
        "success": True,
        "session_id": session_id,
        "task": task,
        "workspace": workspace,
    })


@app.route("/status/<session_id>")
def get_status(session_id):
    with _sessions_lock:
        state = _sessions.get(session_id)
    if state is None:
        return jsonify({"error": "Session not found"}), 404

    # return the last N log entries the frontend hasn't seen
    after = request.args.get("after", type=int, default=0)
    new_logs = state["logs"][after:] if state["logs"] else []

    return jsonify({
        "session_id": session_id,
        "status": state["status"],
        "steps": state["steps"],
        "finish_reason": state["finish_reason"],
        "stop_reason": state["stop_reason"],
        "error": state["error"],
        "waiting_for_approval": state["waiting_for_approval"],
        "pending_action": state["pending_action"],
        "log_count": len(state["logs"]),
        "new_logs": new_logs,
    })


@app.route("/approve/<session_id>", methods=["POST"])
def approve_action(session_id):
    with _sessions_lock:
        state = _sessions.get(session_id)
    if state is None:
        return jsonify({"error": "Session not found"}), 404
    if not state["waiting_for_approval"]:
        return jsonify({"error": "No pending approval"}), 400

    state["approval_decision"] = True
    state["approval_event"].set()
    return jsonify({"success": True, "decision": "approved"})


@app.route("/reject/<session_id>", methods=["POST"])
def reject_action(session_id):
    with _sessions_lock:
        state = _sessions.get(session_id)
    if state is None:
        return jsonify({"error": "Session not found"}), 404
    if not state["waiting_for_approval"]:
        return jsonify({"error": "No pending approval"}), 400

    state["approval_decision"] = False
    state["approval_event"].set()
    return jsonify({"success": True, "decision": "rejected"})


# ---------------------------------------------------------------------------
# frontend — single-page HTML with embedded CSS + JS
# ---------------------------------------------------------------------------

INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeGuard WebUI</title>
<style>
  :root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --surface2: #0f3460;
    --accent: #e94560;
    --accent2: #53d769;
    --text: #e0e0e0;
    --text-dim: #999;
    --border: #333;
    --danger: #e94560;
    --warning: #f0a500;
    --success: #53d769;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    padding: 24px;
  }
  .container {
    width: 100%;
    max-width: 860px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  h1 {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.5px;
  }
  h1 span { color: var(--accent); }

  /* ---- form row ---- */
  .form-row {
    display: flex;
    gap: 10px;
  }
  .form-row input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-size: 0.95rem;
    outline: none;
    transition: border-color .2s;
  }
  .form-row input:focus { border-color: var(--accent); }
  .form-row button {
    padding: 10px 24px;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .2s;
  }
  .form-row button:hover { opacity: 0.85; }
  .form-row button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ---- status bar ---- */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 0.85rem;
    color: var(--text-dim);
  }
  .status-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-dot.running { background: var(--warning); animation: pulse 1.2s infinite; }
  .status-dot.waiting { background: var(--danger); animation: pulse 0.6s infinite; }
  .status-dot.completed { background: var(--success); }
  .status-dot.error { background: var(--danger); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }

  /* ---- log area ---- */
  .log-area {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    height: 420px;
    overflow-y: auto;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .log-area:empty::after {
    content: 'Waiting for task to start …';
    color: var(--text-dim);
    font-style: italic;
  }
  .log-entry { margin-bottom: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .log-entry .ts { color: var(--text-dim); margin-right: 8px; }
  .log-entry.step   { color: #7ec8e3; }
  .log-entry.executed { color: var(--success); }
  .log-entry.blocked { color: var(--warning); }
  .log-entry.awaiting_approval { color: var(--danger); font-weight: 700; }
  .log-entry.completed { color: var(--accent2); font-weight: 700; }
  .log-entry.error  { color: var(--danger); }

  /* ---- modal ---- */
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.65);
    z-index: 1000;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.active { display: flex; }
  .modal-box {
    background: var(--surface);
    border: 1px solid var(--danger);
    border-radius: 14px;
    padding: 28px 32px;
    max-width: 480px;
    width: 90%;
    box-shadow: 0 8px 40px rgba(233,68,96,0.25);
  }
  .modal-box h2 {
    font-size: 1.2rem;
    margin-bottom: 16px;
    color: var(--danger);
  }
  .modal-box .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 0.88rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .modal-box .detail-row .label { color: var(--text-dim); }
  .modal-box .detail-row .value { font-weight: 600; max-width: 280px; overflow: hidden; text-overflow: ellipsis; }
  .modal-box .btn-row {
    display: flex;
    gap: 12px;
    margin-top: 22px;
    justify-content: flex-end;
  }
  .modal-box .btn-row button {
    padding: 10px 28px;
    border: none;
    border-radius: 8px;
    font-size: 0.92rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .2s;
  }
  .modal-box .btn-approve { background: var(--success); color: #111; }
  .modal-box .btn-reject  { background: var(--danger);  color: #fff; }
  .modal-box .btn-row button:hover { opacity: 0.8; }
</style>
</head>
<body>
<div class="container">

  <h1>🛡️ CodeGuard <span>WebUI</span></h1>

  <div class="form-row">
    <input id="task-input" type="text" placeholder="Task description, e.g. delete test.txt"
           value="delete test.txt" autofocus>
    <button id="run-btn" onclick="startTask()">▶ Run</button>
  </div>

  <div class="status-bar">
    Status: <span class="status-dot" id="status-dot"></span>
    <span id="status-label">Idle</span>
    &nbsp;|&nbsp; Steps: <strong id="steps-count">0</strong>
    &nbsp;|&nbsp; <span id="finish-label"></span>
  </div>

  <div class="log-area" id="log-area"></div>

</div>

<!-- approval modal -->
<div class="modal-overlay" id="modal-overlay">
  <div class="modal-box">
    <h2>⚠ High-Risk Action Requires Approval</h2>
    <div id="modal-details"></div>
    <div class="btn-row">
      <button class="btn-approve" onclick="submitDecision(true)">✓ Approve</button>
      <button class="btn-reject"  onclick="submitDecision(false)">✗ Reject</button>
    </div>
  </div>
</div>

<script>
  let sessionId = null;
  let pollTimer = null;
  let logCount = 0;
  let awaitingApproval = false;

  function setStatus(cls, label) {
    const dot = document.getElementById('status-dot');
    dot.className = 'status-dot ' + cls;
    document.getElementById('status-label').textContent = label;
  }

  function appendLog(entry) {
    const area = document.getElementById('log-area');
    const div = document.createElement('div');
    div.className = 'log-entry ' + (entry.type || '');
    const ts = entry.timestamp ? entry.timestamp.slice(11,19) : '';
    let text = '';
    if (entry.type === 'step') {
      const a = entry.data && entry.data.action ? entry.data.action : {};
      text = '[' + ts + '] Step ' + (entry.data.step || '?') + ': ' + (a.action || '?')
           + (a.path ? ' ' + a.path : '') + (a.command ? ' ' + a.command : '');
    } else if (entry.type === 'executed') {
      const r = entry.data && entry.data.result ? entry.data.result : {};
      text = '[' + ts + '] Executed → ' + (r.success ? 'OK' : 'FAILED')
           + (r.error ? ': ' + r.error : '');
    } else if (entry.type === 'blocked') {
      text = '[' + ts + '] BLOCKED — ' + (entry.data && entry.data.reason || '');
    } else if (entry.type === 'awaiting_approval') {
      text = '[' + ts + '] ⏳ AWAITING APPROVAL …';
    } else if (entry.type === 'completed') {
      text = '[' + ts + '] ✅ COMPLETED — ' + (entry.data && entry.data.finish_reason || '');
    } else if (entry.type === 'error') {
      text = '[' + ts + '] ❌ ERROR — ' + (entry.data && entry.data.error || '');
    } else {
      text = '[' + ts + '] ' + JSON.stringify(entry);
    }
    div.textContent = text;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
  }

  function showModal(action) {
    const details = document.getElementById('modal-details');
    let html = '';
    const rows = [
      ['Action', action.action || 'unknown'],
      ['Risk Level', action.risk_level || '?'],
      ['Rule', action.rule || ''],
      ['Path', action.path || '—'],
      ['Command', action.command || '—'],
    ];
    if (action.content_preview) {
      rows.push(['Content Preview', action.content_preview]);
    }
    rows.forEach(function(r) {
      if (r[1]) {
        html += '<div class="detail-row"><span class="label">' + r[0] + '</span><span class="value">' + r[1] + '</span></div>';
      }
    });
    details.innerHTML = html;
    document.getElementById('modal-overlay').classList.add('active');
  }

  function hideModal() {
    document.getElementById('modal-overlay').classList.remove('active');
  }

  function submitDecision(approved) {
    if (!sessionId) return;
    const url = approved ? '/approve/' + sessionId : '/reject/' + sessionId;
    fetch(url, { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          awaitingApproval = false;
          hideModal();
          setStatus('running', 'Running');
        }
      });
  }

  function pollStatus() {
    if (!sessionId) return;
    fetch('/status/' + sessionId + '?after=' + logCount)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) return;

        // append new logs
        if (data.new_logs && data.new_logs.length > 0) {
          data.new_logs.forEach(function(entry) { appendLog(entry); });
          logCount = data.log_count;
        }

        document.getElementById('steps-count').textContent = data.steps || 0;

        // handle approval modal
        if (data.waiting_for_approval && !awaitingApproval) {
          awaitingApproval = true;
          setStatus('waiting', 'Awaiting Approval');
          showModal(data.pending_action || {});
        }
        if (!data.waiting_for_approval && awaitingApproval) {
          awaitingApproval = false;
          hideModal();
        }

        // handle completion
        if (data.status === 'completed') {
          setStatus('completed', 'Completed');
          document.getElementById('finish-label').textContent = data.finish_reason || '';
          stopPolling();
        } else if (data.status === 'error') {
          setStatus('error', 'Error');
          document.getElementById('finish-label').textContent = data.error || '';
          stopPolling();
        } else if (!data.waiting_for_approval) {
          setStatus('running', 'Running');
        }
      });
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 1000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    document.getElementById('run-btn').disabled = false;
  }

  function startTask() {
    const task = document.getElementById('task-input').value.trim();
    if (!task) return;

    // reset UI
    document.getElementById('log-area').innerHTML = '';
    document.getElementById('steps-count').textContent = '0';
    document.getElementById('finish-label').textContent = '';
    logCount = 0;
    awaitingApproval = false;
    hideModal();
    document.getElementById('run-btn').disabled = true;
    setStatus('running', 'Starting …');

    fetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'task=' + encodeURIComponent(task)
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          sessionId = data.session_id;
          setStatus('running', 'Running');
          startPolling();
        } else {
          setStatus('error', 'Failed to start');
          document.getElementById('run-btn').disabled = false;
        }
      })
      .catch(function() {
        setStatus('error', 'Connection error');
        document.getElementById('run-btn').disabled = false;
      });
  }

  // start on Enter key
  document.getElementById('task-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') startTask();
  });
</script>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
