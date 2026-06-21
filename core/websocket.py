# core/websocket.py
# WebSocket handler menggunakan Flask-SocketIO.
# Bertanggung jawab untuk:
#   1. Relay event QR code ke semua client React yang terkoneksi
#   2. Relay event docking (aligned / lost)
#   3. Background thread yang drain queue dari camera_bottom
#
# React client connect ke: ws://ip:8000  (same port sebagai REST API)
# SocketIO events yang di-emit ke client:
#   "qr_detected"   → { data, aligned, timestamp }
#   "dock_aligned"  → { aligned, timestamp }
#   "dock_lost"     → { aligned, timestamp }

import threading
import logging
import multiprocessing
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

# socketio instance — di-init di routes.py dan di-share ke sini
socketio: SocketIO | None = None


def init_socketio(sio: SocketIO):
    """Inject SocketIO instance dari routes.py."""
    global socketio
    socketio = sio


# ──────────────────────────────────────────────
# SocketIO event handlers (dari React ke server)
# ──────────────────────────────────────────────
def register_handlers(sio: SocketIO):
    """Register semua event handler SocketIO."""

    @sio.on("connect")
    def on_connect(auth=None):
        logger.info(f"[WS] Client baru terkoneksi")
        # Kirim state terakhir ke client yang baru join
        sio.emit("server_info", {
            "message": "Terhubung ke ROV Core",
            "streams": {
                "front":  "http://<ip>:8001/stream",
                "bottom": "http://<ip>:8002/stream",
            }
        })

    @sio.on("disconnect")
    def on_disconnect():
        logger.info(f"[WS] Client disconnect")

    @sio.on("ping_rov")
    def on_ping(data):
        """Client bisa ping untuk cek latensi."""
        sio.emit("pong_rov", {"echo": data})


# ──────────────────────────────────────────────
# Queue drainer — background thread di core
# ──────────────────────────────────────────────
def start_queue_drainer(
    qr_result_queue:  multiprocessing.Queue,
    dock_event_queue: multiprocessing.Queue,
):
    """
    Start background threads yang terus-menerus drain queue dari camera_bottom
    dan forward event ke React via SocketIO.
    """
    threading.Thread(
        target=_drain_qr_queue,
        args=(qr_result_queue,),
        daemon=True,
        name="QRQueueDrainer"
    ).start()

    threading.Thread(
        target=_drain_dock_queue,
        args=(dock_event_queue,),
        daemon=True,
        name="DockQueueDrainer"
    ).start()

    logger.info("[WS] Queue drainer threads dimulai")


def _drain_qr_queue(queue: multiprocessing.Queue):
    """Drain qr_result_queue dan emit ke semua WebSocket client."""
    while True:
        try:
            payload = queue.get(timeout=1.0)  # block max 1 detik
            logger.debug(f"[WS] QR dari queue: {payload}")
            if socketio:
                socketio.emit("qr_detected", payload)
        except Exception:
            pass  # timeout normal, lanjut loop


def _drain_dock_queue(queue: multiprocessing.Queue):
    """Drain dock_event_queue dan emit ke semua WebSocket client."""
    while True:
        try:
            payload = queue.get(timeout=1.0)
            event_name = payload.get("type", "dock_event")
            logger.debug(f"[WS] Dock event: {event_name}")
            if socketio:
                socketio.emit(event_name, payload)
        except Exception:
            pass