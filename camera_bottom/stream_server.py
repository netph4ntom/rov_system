# camera_bottom/stream_server.py
# MJPEG server untuk kamera bawah sekaligus menjalankan QR scan loop.
#
# Proses ini melakukan dua hal sekaligus:
#   1. Stream MJPEG ke React (port 8002)
#   2. Scan QR code setiap frame dan push ke shared queue
#
# Thread model:
#   - Thread utama Flask untuk HTTP /stream
#   - Thread background untuk QR scanning (supaya tidak blocking stream)
#
# Endpoint:
#   GET /stream  → MJPEG stream
#   GET /health  → status kamera + QR terakhir
#
# Fix:
#   - scan() sekarang unpack 3 nilai: qr_data, aligned, bbox
#   - update_bbox(bbox) dipanggil agar overlay bbox muncul di stream

import cv2
import threading
import logging
import multiprocessing
from flask import Flask, Response, jsonify

from camera_bottom.camera           import BottomCamera
from camera_bottom.image_processing import BottomImageProcessor
from camera_bottom.qr_detector      import QRDetector
from config import PORT_STREAM_BOTTOM, MJPEG_QUALITY

logger = logging.getLogger(__name__)
app = Flask(__name__)

_camera    : BottomCamera | None          = None
_processor : BottomImageProcessor | None = None
_detector  : QRDetector | None           = None

_current_frame = None
_frame_lock    = threading.Lock()


# ──────────────────────────────────────────────
# Background thread: baca kamera + scan QR
# ──────────────────────────────────────────────
def _capture_and_scan_loop():
    global _current_frame, _camera, _processor, _detector

    while True:
        ret, frame = _camera.read_frame()
        if not ret or frame is None:
            continue

        # Preprocessing khusus QR (grayscale + threshold)
        preprocessed = _processor.preprocess_for_qr(frame)

        # Scan QR — unpack 3 nilai (qr_data, aligned, bbox)
        qr_data, aligned, bbox = _detector.scan(frame, preprocessed)

        # Update state processor — termasuk bbox agar overlay muncul
        _processor.update_qr_data(qr_data)
        _processor.update_dock_status(aligned)
        _processor.update_bbox(bbox)          # ← fix: bbox dikirim ke processor

        # Proses frame untuk stream (sharpening + HUD + bbox overlay)
        display_frame = _processor.process(frame.copy())

        with _frame_lock:
            _current_frame = display_frame


# ──────────────────────────────────────────────
# MJPEG generator
# ──────────────────────────────────────────────
def _generate_frames():
    global _current_frame
    while True:
        with _frame_lock:
            frame = _current_frame

        if frame is None:
            continue

        ret, buffer = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, MJPEG_QUALITY]
        )
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buffer.tobytes()
            + b"\r\n"
        )


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.route("/stream")
def stream():
    return Response(
        _generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/health")
def health():
    global _camera, _processor
    cam_ok = bool(_camera and _camera.cap and _camera.cap.isOpened())
    return jsonify({
        "camera":       "bottom",
        "status":       "ok" if cam_ok else "error",
        "last_qr":      _processor._last_qr_data if _processor else None,
        "dock_aligned": _processor._dock_aligned if _processor else False,
    })


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def run_bottom_stream_server(
    qr_result_queue:  multiprocessing.Queue,
    dock_event_queue: multiprocessing.Queue,
):
    global _camera, _processor, _detector

    logging.basicConfig(level=logging.INFO)
    logger.info("[BottomStream] Proses dimulai")

    _camera    = BottomCamera()
    _processor = BottomImageProcessor(show_hud=True)
    _detector  = QRDetector(qr_result_queue, dock_event_queue)

    capture_thread = threading.Thread(
        target=_capture_and_scan_loop,
        daemon=True,
        name="BottomCaptureThread"
    )
    capture_thread.start()

    logger.info(f"[BottomStream] MJPEG server berjalan di port {PORT_STREAM_BOTTOM}")
    app.run(
        host="0.0.0.0",
        port=PORT_STREAM_BOTTOM,
        threaded=True,
        use_reloader=False
    )