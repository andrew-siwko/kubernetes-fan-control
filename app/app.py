import json
import logging
import os
import socket
import threading

from flask import Flask, Response, jsonify, render_template

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BROADCAST_IP = os.environ.get("BROADCAST_IP", "192.168.50.255")
BROADCAST_PORT = int(os.environ.get("BROADCAST_PORT", "12345"))

COMMANDS = {
    "low": {"low": "on"},
    "medium": {"medium": "on"},
    "high": {"high": "on"},
    "off": {"off": "off"},
    "light": {"lights": "toggle"},
    "status": {"status": "true"},
}

latest_status = None
status_lock = threading.Lock()
status_event = threading.Event()


def record_status(status_payload):
    global latest_status
    with status_lock:
        latest_status = status_payload
    status_event.set()


def status_listener():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", BROADCAST_PORT))
        app.logger.info("Started fan status listener on port %s", BROADCAST_PORT)
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                payload = json.loads(data.decode("utf-8"))
                status_payload = payload.get("current_status") or payload.get("status")
                if isinstance(status_payload, dict):
                    record_status(status_payload)
                    app.logger.info("Received async fan status from %s: %s", addr, status_payload)
            except json.JSONDecodeError as exc:
                app.logger.warning("Failed to decode incoming status payload: %s", exc)
            except Exception as exc:
                app.logger.debug("Fan status listener error: %s", exc)


def start_status_listener():
    worker_id = os.environ.get("GUNICORN_WORKER_ID")
    if worker_id is not None and worker_id != "1":
        app.logger.info("Skipping status listener startup in gunicorn worker %s", worker_id)
        return

    listener_thread = threading.Thread(target=status_listener, daemon=True)
    listener_thread.start()


start_status_listener()


def send_udp_broadcast(payload: dict):
    message = json.dumps(payload).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.sendto(message, (BROADCAST_IP, BROADCAST_PORT))
        app.logger.info("Sent %s to %s:%s", message, BROADCAST_IP, BROADCAST_PORT)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify(status="ok")


@app.route("/api/status")
def status():
    with status_lock:
        return jsonify(status=latest_status or {})


@app.route("/api/status/stream")
def status_stream():
    def event_stream():
        last_sent = None
        while True:
            status_event.wait(timeout=10)
            with status_lock:
                current_status = latest_status
            if current_status != last_sent:
                last_sent = current_status
                yield f"data: {json.dumps(current_status or {})}\n\n"
            else:
                yield ": heartbeat\n\n"
            status_event.clear()
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/command/<name>", methods=["POST"])
def command(name):
    payload = COMMANDS.get(name)
    if payload is None:
        return jsonify(error=f"unknown command '{name}'"), 400
    try:
        response = send_udp_broadcast(payload)
    except OSError as exc:
        app.logger.exception("Failed to send UDP broadcast")
        return jsonify(error=str(exc)), 500
    return jsonify(status="sent", command=name, payload=payload, fanStatus=response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
