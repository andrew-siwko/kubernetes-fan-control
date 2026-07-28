import json
import logging
import os
import socket

from flask import Flask, jsonify, render_template

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
}


def send_udp_broadcast(payload: dict) -> None:
    message = json.dumps(payload).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(message, (BROADCAST_IP, BROADCAST_PORT))
    app.logger.info("Sent %s to %s:%s", message, BROADCAST_IP, BROADCAST_PORT)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify(status="ok")


@app.route("/api/command/<name>", methods=["POST"])
def command(name):
    payload = COMMANDS.get(name)
    if payload is None:
        return jsonify(error=f"unknown command '{name}'"), 400
    try:
        send_udp_broadcast(payload)
    except OSError as exc:
        app.logger.exception("Failed to send UDP broadcast")
        return jsonify(error=str(exc)), 500
    return jsonify(status="sent", command=name, payload=payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
