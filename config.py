# config.py - Konfigurasi global untuk Project ROV Vision
# Semua konstanta dan setting dipusatkan di sini

# ──────────────────────────────────────────────
# KAMERA
# ──────────────────────────────────────────────
CAMERA_FRONT_INDEX   = 1          # index /dev/videoX untuk kamera depan
CAMERA_BOTTOM_INDEX  = 0          # index /dev/videoX untuk kamera bawah

FRAME_WIDTH   = 640
FRAME_HEIGHT  = 480
FRAME_FPS     = 30

MJPEG_QUALITY = 80                # kualitas JPEG 1–100 (makin kecil makin ringan)

# ------------------------------------------------
# IMAGE PROCESSING
# ------------------------------------------------

# ── Color correction (camera_front) ──────────────────────────
# Naikkan RED_BOOST jika gambar masih terlalu biru/hijau.
COLOR_CORRECTION_RED_BOOST   = 10   # range rekomendasi: 5–20
COLOR_CORRECTION_BLUE_REDUCE =  5   # range rekomendasi: 0–10

# ── CLAHE (camera_front & camera_bottom) ─────────────────────
CLAHE_CLIP_LIMIT = 1.5        # range rekomendasi kolam: 1.0–2.0
CLAHE_TILE_SIZE  = (8, 8)     # tile 8x8 cocok untuk resolusi 640x480

# ──────────────────────────────────────────────
# SERVER PORT
# ──────────────────────────────────────────────
# MJPEG stream
PORT_STREAM_FRONT   = 8001        # http://<ip>:8001/stream
PORT_STREAM_BOTTOM  = 8002        # http://<ip>:8002/stream

# Core API (Flask REST + WebSocket via flask-socketio)
PORT_CORE_API        = 8000       # http://<ip>:8000/

# ──────────────────────────────────────────────
# MULTIPROCESSING / IPC
# ──────────────────────────────────────────────
# Queue maxsize = 0 berarti unlimited; set ke N untuk back-pressure
QUEUE_MAXSIZE = 10

# ──────────────────────────────────────────────
# QR CODE / DOCKING
# ──────────────────────────────────────────────
QR_SCAN_INTERVAL_MS = 200         # scan QR setiap N ms (kurangi beban CPU)

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
import os
LOG_DIR   = os.path.join(os.path.dirname(__file__), "logs")
LOG_LEVEL = "DEBUG"               # DEBUG | INFO | WARNING | ERROR