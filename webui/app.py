"""CodeGuard WebUI — Flask-based web interface.

Provides browser-based access to the CodeGuard agent with interactive
approval and task management capabilities.
"""

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

INDEX_TEMPLATE = """<!DOCTYPE html>
<html>
<head><title>CodeGuard WebUI</title></head>
<body>
    <h1>CodeGuard WebUI</h1>
    <p>Status: Running</p>
    <form method="post" action="/run">
        <input name="task" placeholder="Task description" style="width:300px">
        <button type="submit">Run</button>
    </form>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(INDEX_TEMPLATE)


@app.route("/status")
def status():
    return jsonify({"status": "ok", "service": "codeguard"})


@app.route("/run", methods=["POST"])
def run_task():
    task = request.form.get("task", "")
    if not task:
        return jsonify({"success": False, "error": "No task provided"}), 400
    return jsonify({"success": True, "task": task, "status": "submitted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)