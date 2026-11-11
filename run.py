# -*- coding: utf-8 -*-
"""Lanzador de Radar Laboral: servidor local + ventana nativa."""
from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import uvicorn  # noqa: E402


def esperar(url: str, timeout: float = 25.0) -> bool:
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as respuesta:
                if respuesta.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Radar Laboral")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-window", action="store_true", help="Solo servidor, sin ventana")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info" if args.verbose else "warning",
    )
    servidor = uvicorn.Server(config)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()

    if not esperar(url + "/api/health"):
        print("No se pudo iniciar el servidor local.", file=sys.stderr)
        servidor.should_exit = True
        return 1

    if args.no_window:
        print(f"Radar Laboral en {url}  (Ctrl+C para salir)")
        try:
            while hilo.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        servidor.should_exit = True
        hilo.join(timeout=5)
        return 0

    import webview

    webview.create_window(
        "Radar Laboral",
        url,
        width=1480,
        height=920,
        min_size=(980, 640),
    )
    webview.start()
    servidor.should_exit = True
    hilo.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
