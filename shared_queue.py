# queue.py - Shared queue antar proses menggunakan multiprocessing.Manager
#
# Kenapa pakai Manager().Queue() bukan multiprocessing.Queue() biasa?
# → Manager Queue bisa di-share ke proses yang spawn SETELAH manager dibuat,
#   sedangkan Queue biasa harus di-pass saat fork. Lebih fleksibel untuk arsitektur ini.
#
# Flow data:
#   camera_bottom ──(qr_result_queue)──► core (dikirim ke React via WebSocket)
#   camera_bottom ──(dock_event_queue)──► core (event docking terdeteksi)

import multiprocessing
from config import QUEUE_MAXSIZE


def create_shared_queues(manager: multiprocessing.managers.SyncManager):
    """
    Buat semua queue yang dibutuhkan antar proses.
    Dipanggil sekali di main.py lalu di-pass ke masing-masing proses.

    Returns dict berisi semua queue agar mudah di-unpack.
    """
    queues = {
        # Hasil decode QR code dari camera_bottom → core
        "qr_result":  manager.Queue(maxsize=QUEUE_MAXSIZE),

        # Event docking (ROV sudah align dengan marker) dari camera_bottom → core
        "dock_event": manager.Queue(maxsize=QUEUE_MAXSIZE),

        # (Opsional) frame thumbnail bottom → core untuk health-check / snapshot
        "frame_snapshot": manager.Queue(maxsize=2),  # maxsize kecil, cukup frame terbaru
    }
    return queues