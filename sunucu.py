#!/usr/bin/env python3
"""
index.html'i yerel olarak sunar; sayfadaki butona basilinca bayrak_glyph.py'yi acar.

Kullanim (uc dosya ayni klasorde olmali: sunucu.py, index.html, bayrak_glyph.py):
    python sunucu.py                 -> tarayici otomatik acilir
    python sunucu.py portre.png      -> portre dosyasini da gecirir

Durdurmak icin terminalde Ctrl+C.
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

KLASOR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(KLASOR, "bayrak_glyph.py")
HTML = os.path.join(KLASOR, "index.html")
HOST, PORT = "127.0.0.1", 8765          # yalnizca bu bilgisayardan erisilir

# Portre: komut satirindan ya da klasordeki portre.png / portre.jpg
portre = sys.argv[1] if len(sys.argv) > 1 else None
if portre is None:
    for ad in ("portre.png", "portre.jpg", "portre.jpeg"):
        yol = os.path.join(KLASOR, ad)
        if os.path.exists(yol):
            portre = yol
            break

surec = None


class Isleyici(BaseHTTPRequestHandler):
    def _json(self, kod, veri):
        govde = json.dumps(veri).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(HTML, "rb") as f:
                govde = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
        else:
            self._json(404, {"hata": "bulunamadi"})

    def do_POST(self):
        global surec
        if self.path != "/calistir":
            return self._json(404, {"hata": "bulunamadi"})
        # baska siteler butonu tetikleyemesin
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return self._json(403, {"hata": "izin yok"})
        if not os.path.exists(SCRIPT):
            return self._json(500, {"hata": "bayrak_glyph.py bulunamadi"})
        if surec is not None and surec.poll() is None:
            return self._json(200, {"durum": "zaten acik"})
        komut = [sys.executable, SCRIPT]
        if portre:
            komut.append(portre)
        surec = subprocess.Popen(komut, cwd=KLASOR)
        self._json(200, {"durum": "acildi"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    adres = f"http://{HOST}:{PORT}/"
    print("Sayfa:", adres)
    print("Portre:", portre or "yok (sadece bayrak cikar)")
    print("Durdurmak icin Ctrl+C")
    threading.Timer(0.6, lambda: webbrowser.open(adres)).start()
    try:
        HTTPServer((HOST, PORT), Isleyici).serve_forever()
    except KeyboardInterrupt:
        pass
