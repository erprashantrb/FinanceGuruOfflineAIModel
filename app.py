from flask import Flask, render_template, request, jsonify
import subprocess
import threading
import requests
import time
import os
import glob
import signal
from werkzeug.utils import secure_filename


# App Initialization

app = Flask(__name__)


# Configuration

app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024 * 1024  # 6 GB

UPLOAD_DIR = "uploads"
LOG_DIR = "model_logs"
ALLOWED_EXT = {".gguf"}

RUN_BAT = r"C:\Users\prash\Downloads\GGUF CHATGPT\run_model.bat"
MODEL_PORT = 8080

HEALTH_URL = f"http://127.0.0.1:{MODEL_PORT}/health"
COMPLETION_URL = f"http://127.0.0.1:{MODEL_PORT}/completion"

# =========================
# Global State
# =========================
MODEL_PROCESS = None
MODEL_READY = False
MODEL_LOCK = threading.Lock()

# =========================
# PROFESSIONAL SYSTEM PROMPT
# =========================
SYSTEM_PROMPT = """
You are OFinanceGPT, a professional financial assistant.

Answer questions about finance, banking, payments, savings,
investing, and money management.

Rules:
- Be accurate and factual.
- Correct wrong statements politely.
- Keep answers clear and simple.
- Use bullet points when helpful.
- If unsure, say you are unsure.

Tone:
- Professional and neutral.


"""

# =========================
# Helpers
# =========================
def is_allowed_filename(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT

def build_llama3_prompt(user_message: str) -> str:
    """
    Build a correct LLaMA-3.x chat prompt.
    THIS IS MANDATORY for system prompt enforcement.
    """
    return f"""<|begin_of_text|>
<|start_header_id|>system<|end_header_id|>
{SYSTEM_PROMPT.strip()}
<|eot_id|>
<|start_header_id|>user<|end_header_id|>
{user_message.strip()}
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
"""

def kill_process_tree(proc):
    try:
        pid = proc.pid
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

        if proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False)
    except Exception:
        pass

def start_llama_server(model_path: str):
    global MODEL_PROCESS, MODEL_READY
    MODEL_READY = False

    abs_model_path = os.path.abspath(model_path)
    os.makedirs(LOG_DIR, exist_ok=True)

    with MODEL_LOCK:
        if MODEL_PROCESS and MODEL_PROCESS.poll() is None:
            kill_process_tree(MODEL_PROCESS)
            time.sleep(1)

        if not os.path.exists(RUN_BAT):
            print("run_model.bat not found")
            return

        stdout_log = open(os.path.join(LOG_DIR, "stdout.log"), "ab")
        stderr_log = open(os.path.join(LOG_DIR, "stderr.log"), "ab")

        MODEL_PROCESS = subprocess.Popen(
            [RUN_BAT, abs_model_path],
            stdout=stdout_log,
            stderr=stderr_log,
            shell=False,
            creationflags=0x00000200 if os.name == "nt" else 0
        )

    # Wait for model health
    for _ in range(90):
        try:
            r = requests.get(HEALTH_URL, timeout=2)
            if r.status_code == 200:
                MODEL_READY = True
                return
        except Exception:
            pass
        time.sleep(2)

def start_model_async(model_path: str):
    threading.Thread(
        target=start_llama_server,
        args=(model_path,),
        daemon=True
    ).start()

def latest_model():
    files = sorted(
        glob.glob(os.path.join(UPLOAD_DIR, "*.gguf")),
        key=os.path.getmtime,
        reverse=True
    )
    return files[0] if files else None

# =========================
# Routes
# =========================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["GET"])
def chat_page():
    return render_template("chat.html")

@app.route("/upload", methods=["POST"])
def upload_model():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    if not is_allowed_filename(filename):
        return jsonify({"error": "Only .gguf models are allowed"}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    for old in glob.glob(os.path.join(UPLOAD_DIR, "*.gguf")):
        try:
            os.remove(old)
        except Exception:
            pass

    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)

    start_model_async(path)

    return jsonify({"status": "Model uploaded. Starting server..."})

@app.route("/check_status")
def check_status():
    return jsonify({"ready": MODEL_READY})

@app.route("/reload", methods=["POST"])
def reload_model():
    model = latest_model()
    if not model:
        return jsonify({"error": "No model found"}), 404

    start_model_async(model)
    return jsonify({"status": "Reloading model..."})

@app.route("/chat", methods=["POST"])
def chat_api():
    if not MODEL_READY:
        return jsonify({"reply": "Model is not ready yet."}), 503

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a valid message."}), 400

    prompt = build_llama3_prompt(user_message)

    try:
        res = requests.post(
            COMPLETION_URL,
            json={
                "prompt": prompt,
                "n_predict": 512,
                "temperature": 0.4,
                "top_p": 0.85,
                "repeat_penalty": 1.2,
                "stream": False
            },
            timeout=90
        )

        output = res.json()
        reply = output.get("content", "").strip()

        if not reply:
            reply = "No response generated."

    except Exception as e:
        reply = f"Model error: {e}"

    return jsonify({"reply": reply})

# =========================
# Shutdown Cleanup
# =========================
def shutdown():
    global MODEL_PROCESS
    if MODEL_PROCESS and MODEL_PROCESS.poll() is None:
        kill_process_tree(MODEL_PROCESS)

import atexit
atexit.register(shutdown)

# =========================
# Run Server
# =========================
if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False)
