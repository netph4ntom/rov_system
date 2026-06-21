# camera_front/stream_server.py
# MJPEG streaming server untuk kamera depan menggunakan Flask.
#
# Kenapa MJPEG?
#   - Latensi rendah, tidak butuh browser support WebRTC
#   - Compatible langsung dengan <img src="http://ip:8001/stream"> di React
#   - Mudah di-debug (buka di browser biasa)
#
# Endpoint:
#   GET /stream  → multipart/x-mixed-replace MJPEG
#   GET /health  → JSON status kamera
#
# Perubahan dari versi sebelumnya:
#   - Capture thread dipisahkan dari Flask thread (sama dengan bottom)
#     → mencegah race condition cv2.VideoCapture kalau 2 client buka /stream
#   - _frame_id counter: stream thread skip encode kalau frame belum berubah
#     → mengurangi lag dan CPU usage
#   - Busy-wait diganti sleep(5ms / 10ms)
#   - GeneratorExit di-handle untuk detect client disconnect
#   - Capture thread dibungkus try/except agar crash tidak silent
#   - debug=False eksplisit di app.run()
#   - import time ditambahkan

import time
import threading
import logging
import multiprocessing

import cv2
from flask import Flask, Response, jsonify

from camera_front.camera import FrontCamera
from camera_front.image_processing import FrontImageProcessor
from config import PORT_STREAM_FRONT, MJPEG_QUALITY

logger = logging.getLogger(__name__)
app = Flask(__name__)

# ──────────────────────────────────────────────
# Shared state antara capture thread dan stream thread
# ──────────────────────────────────────────────
_camera    : FrontCamera | None          = None
_processor : FrontImageProcessor | None  = None

_current_frame = None
_frame_lock    = threading.Lock()
_frame_id      = 0   # increment tiap frame baru — stream thread skip encode kalau sama


# ──────────────────────────────────────────────
# Background thread: baca kamera + proses frame
# ──────────────────────────────────────────────
def _capture_loop():
    """
    Loop berjalan di background thread.
    Baca frame → proses (color correction, CLAHE, HUD) → simpan untuk stream.

    Dipisah dari Flask thread agar cv2.VideoCapture tidak diakses dari
    multiple thread sekaligus (tidak thread-safe).

    Dibungkus try/except agar crash tidak silent (stream freeze tanpa log).
    """
    global _current_frame, _frame_id

    try:
        while True:
            ret, frame = _camera.read_frame()
            if not ret or frame is None:
                # Kamera disconnect atau belum siap — jangan busy-wait
                time.sleep(0.01)
                continue

            # Proses frame (color correction, CLAHE, HUD)
            display_frame = _processor.process(frame)

            with _frame_lock:
                _current_frame = display_frame
                _frame_id += 1

    except Exception as e:
        logger.critical(
            f"[FrontStream] Capture thread crash, stream berhenti: {e}",
            exc_info=True
        )


# ──────────────────────────────────────────────
# MJPEG generator
# ──────────────────────────────────────────────
def _generate_frames():
    """
    Generator MJPEG.
    - Hanya encode kalau ada frame BARU (_frame_id berubah) → kurangi lag & CPU
    - frame.copy() di dalam lock → hindari torn read dari capture thread
    - Sleep 5ms saat frame belum berubah (bukan busy-wait)
    - GeneratorExit di-catch → log saat client disconnect
    """
    last_id = -1

    while True:
        with _frame_lock:
            if _current_frame is None or _frame_id == last_id:
                frame = None
            else:
                frame   = _current_frame.copy()
                last_id = _frame_id

        if frame is None:
            time.sleep(0.005)
            continue

        ret, buffer = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, MJPEG_QUALITY]
        )
        if not ret:
            continue

        try:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
        except GeneratorExit:
            logger.info("[FrontStream] Client disconnect dari /stream")
            return


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.route("/stream")
def stream():
    """Endpoint MJPEG utama. Buka di browser atau <img> tag React."""
    return Response(
        _generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/health")
def health():
    """Health check sederhana untuk monitoring."""
    cam_ok = bool(_camera and _camera.cap and _camera.cap.isOpened())
    return jsonify({
        "camera": "front",
        "status": "ok" if cam_ok else "error",
    })


# ──────────────────────────────────────────────
# Entry point (dipanggil oleh main.py sebagai proses)
# ──────────────────────────────────────────────
def run_front_stream_server():
    """
    Fungsi ini dijalankan sebagai proses terpisah oleh main.py.
    Menginisialisasi kamera lalu start Flask server.
    """
    global _camera, _processor

    logging.basicConfig(level=logging.INFO)
    logger.info("[FrontStream] Proses dimulai")

    _camera    = FrontCamera()
    _processor = FrontImageProcessor(show_hud=True)

    # Start background capture thread
    capture_thread = threading.Thread(
        target=_capture_loop,
        daemon=True,
        name="FrontCaptureThread"
    )
    capture_thread.start()

    logger.info(f"[FrontStream] MJPEG server berjalan di port {PORT_STREAM_FRONT}")
    app.run(
        host="0.0.0.0",
        port=PORT_STREAM_FRONT,
        threaded=True,
        use_reloader=False,
        debug=False,  # eksplisit agar tidak nyala kalau env var FLASK_DEBUG=1
    )


if __name__ == "__main__":
    run_front_stream_server()