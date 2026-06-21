# core/routes.py
# REST API endpoints + inisialisasi Flask app dan SocketIO.
#
# Endpoints:
#   GET  /api/status         → status seluruh sistem ROV
#   GET  /api/streams        → URL stream kamera front dan bottom
#   GET  /api/qr/history     → riwayat QR yang pernah terdeteksi (in-memory)
#   DELETE /api/qr/history   → clear riwayat QR
#   GET  /api/health         → health check cepat

import logging
import multiprocessing
from datetime import datetime
from flask import Flask, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

from core.websocket import init_socketio, register_handlers, start_queue_drainer
from config import PORT_CORE_API, PORT_STREAM_FRONT, PORT_STREAM_BOTTOM

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# State in-memory (sederhana, bisa ganti ke Redis/DB kalau perlu persist)
# ──────────────────────────────────────────────
_qr_history: list[dict] = []  # max 100 entry
QR_HISTORY_MAX = 100


# ──────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────
def create_app() -> tuple[Flask, SocketIO]:
    app = Flask(__name__)

    # CORS: izinkan React dev server (localhost:3000 / localhost:5173)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    sio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading"  # cocok untuk Flask multiprocessing setup
    )

    # Register WebSocket handlers
    init_socketio(sio)
    register_handlers(sio)

    # ── REST Routes ────────────────────────────
    @app.route("/api/status")
    def status():
        return jsonify({
            "service":   "ROV Core API",
            "status":    "running",
            "timestamp": datetime.utcnow().isoformat(),
            "processes": {
                "core":          "running",
                "camera_front":  "running",
                "camera_bottom": "running",
            }
        })

    @app.route("/api/streams")
    def streams():
        """
        Kembalikan URL MJPEG stream.
        React tinggal set <img src={url}> atau gunakan di video player.
        """
        # Ganti <ip> dengan IP Raspberry Pi / host ROV saat deploy
        return jsonify({
            "front": {
                "stream_url": f"http://localhost:{PORT_STREAM_FRONT}/stream",
                "health_url": f"http://localhost:{PORT_STREAM_FRONT}/health",
            },
            "bottom": {
                "stream_url": f"http://localhost:{PORT_STREAM_BOTTOM}/stream",
                "health_url": f"http://localhost:{PORT_STREAM_BOTTOM}/health",
            }
        })

    @app.route("/api/qr/history", methods=["GET"])
    def qr_history_get():
        return jsonify({
            "count":   len(_qr_history),
            "history": _qr_history[-50:]  # kirim 50 terakhir
        })

    @app.route("/api/qr/history", methods=["DELETE"])
    def qr_history_clear():
        _qr_history.clear()
        return jsonify({"message": "QR history cleared"})

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ── SocketIO: simpan QR ke history saat event masuk ──
    @sio.on("qr_detected")
    def _store_qr(data):
        _qr_history.append({**data, "received_at": datetime.utcnow().isoformat()})
        if len(_qr_history) > QR_HISTORY_MAX:
            _qr_history.pop(0)

    return app, sio


# ──────────────────────────────────────────────
# Entry point (dipanggil oleh main.py)
# ──────────────────────────────────────────────
def run_core_server(
    qr_result_queue:  multiprocessing.Queue,
    dock_event_queue: multiprocessing.Queue,
):
    logging.basicConfig(level=logging.INFO)
    logger.info("[CoreAPI] Proses dimulai")

    app, sio = create_app()

    # Start thread yang drain queue → forward ke WebSocket
    start_queue_drainer(qr_result_queue, dock_event_queue)

    logger.info(f"[CoreAPI] Server berjalan di port {PORT_CORE_API}")
    sio.run(
        app,
        host="0.0.0.0",
        port=PORT_CORE_API,
        use_reloader=False,
        log_output=True
    )