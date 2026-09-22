#!/usr/bin/env python3
"""
Pixel de suivi d'ouverture de courriels — mini-clone de icollector.ai.

Principe : chaque pixel est une URL unique qui sert une image invisible de
1x1 pixel. Quand le destinataire ouvre le courriel, son client charge
l'image et le serveur enregistre l'ouverture (date, IP, client).

Usage :
  python3 tracker.py new "Étiquette"   -> crée un pixel, affiche son URL
  python3 tracker.py list              -> liste les pixels et leurs stats
  python3 tracker.py                   -> lance le serveur web

Variables d'environnement :
  PORT        port d'écoute (défaut : 8000)
  BASE_URL    URL publique du serveur, ex. https://abc.trycloudflare.com
              (obligatoire en pratique : sans URL publique, personne
              d'autre que toi ne peut charger le pixel)
  DASH_TOKEN  si défini, le tableau de bord exige ?token=<DASH_TOKEN>
              (recommandé si le serveur est exposé sur Internet)

Dépendances : aucune, Python 3.9+ standard seulement.
"""

import base64
import html
import json
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover
    LOCAL_TZ = timezone.utc

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "pixels.db"))
PORT = int(os.environ.get("PORT", "8000"))
BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{PORT}").rstrip("/")
DASH_TOKEN = os.environ.get("DASH_TOKEN", "")

# PNG 1x1 totalement transparent
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------- base de données

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "CREATE TABLE IF NOT EXISTS pixels("
        "id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, "
        "label TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS opens("
        "id INTEGER PRIMARY KEY, pixel_id INTEGER NOT NULL, "
        "opened_at TEXT NOT NULL, ip TEXT, user_agent TEXT)"
    )
    return con


def create_pixel(label):
    token = secrets.token_urlsafe(16)
    con = db()
    con.execute(
        "INSERT INTO pixels(token, label, created_at) VALUES(?,?,?)",
        (token, label, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()
    return token


def record_open(token, ip, user_agent):
    con = db()
    row = con.execute("SELECT id FROM pixels WHERE token=?", (token,)).fetchone()
    if row:
        con.execute(
            "INSERT INTO opens(pixel_id, opened_at, ip, user_agent) VALUES(?,?,?,?)",
            (row[0], datetime.now(timezone.utc).isoformat(), ip, user_agent[:300]),
        )
        con.commit()
    con.close()


# ---------------------------------------------------------------- utilitaires

def fmt(ts):
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def esc(s):
    return html.escape(str(s or ""))


def client_ip(handler):
    fwd = handler.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return handler.client_address[0]


# ---------------------------------------------------------------- tableau de bord

def dashboard():
    con = db()
    pixels = con.execute(
        "SELECT p.id, p.token, p.label, p.created_at, COUNT(o.id) "
        "FROM pixels p LEFT JOIN opens o ON o.pixel_id = p.id "
        "GROUP BY p.id ORDER BY p.id DESC"
    ).fetchall()
    opens = con.execute(
        "SELECT o.opened_at, p.label, o.ip, o.user_agent "
        "FROM opens o JOIN pixels p ON p.id = o.pixel_id "
        "ORDER BY o.id DESC LIMIT 100"
    ).fetchall()
    con.close()

    rows = []
    for _id, token, label, created, n in pixels:
        url = f"{BASE_URL}/p/{token}.png"
        rows.append(
            f"<tr><td>{esc(label)}</td><td>{fmt(created)}</td>"
            f"<td><strong>{n}</strong></td>"
            f'<td><code>{esc(url)}</code> '
            f"<button onclick=\"navigator.clipboard.writeText('{esc(url)}')\">copier</button></td></tr>"
        )
    orows = [
        f"<tr><td>{fmt(ts)}</td><td>{esc(label)}</td><td>{esc(ip)}</td>"
        f"<td>{esc(ua[:80])}</td></tr>"
        for ts, label, ip, ua in opens
    ]
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pixel tracker</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.88rem;vertical-align:top}}
th{{background:#f2f2f2}}code{{word-break:break-all;font-size:.8rem}}
button{{cursor:pointer}}
</style></head><body>
<h1>&#x1f4e1; Pixel tracker</h1>
<h2>Pixels ({len(pixels)})</h2>
<table><tr><th>Étiquette</th><th>Créé le</th><th>Ouvertures</th><th>URL du pixel</th></tr>
{"".join(rows) or "<tr><td colspan=4>Aucun pixel. Crée-en un avec : <code>python3 tracker.py new &quot;Nom&quot;</code></td></tr>"}
</table>
<h2>Ouvertures récentes</h2>
<table><tr><th>Date (heure de Montréal)</th><th>Pixel</th><th>IP</th><th>Client</th></tr>
{"".join(orows) or "<tr><td colspan=4>Aucune ouverture enregistrée pour l'instant.</td></tr>"}
</table>
<p style="color:#666;font-size:.85rem">Pour glisser un pixel dans un courriel Gmail : rédige ton message, clique sur l'icône image, choisis « Adresse Web (URL) », colle l'URL du pixel, insère-la puis mets-la en taille « Petite ». Elle est invisible (1 pixel transparent).</p>
</body></html>"""


# ---------------------------------------------------------------- serveur HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "PixelTracker/1.0"

    def log_message(self, *args):  # silencieux
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_pixel(self, token):
        record_open(token, client_ip(self), self.headers.get("User-Agent", ""))
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PIXEL_PNG)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(PIXEL_PNG)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/p/") and path.endswith(".png"):
            self._serve_pixel(path[3:-4])
        elif path in ("/", "/dashboard"):
            if DASH_TOKEN and parse_qs(parsed.query).get("token", [""])[0] != DASH_TOKEN:
                self._send(403, "Accès refusé : ?token= requis.")
            else:
                self._send(200, dashboard())
        elif path == "/api/pixels":
            con = db()
            rows = con.execute(
                "SELECT token, label, created_at FROM pixels ORDER BY id DESC"
            ).fetchall()
            con.close()
            self._send(
                200,
                json.dumps(
                    [{"token": t, "label": l, "created_at": c,
                      "url": f"{BASE_URL}/p/{t}.png"} for t, l, c in rows]
                ),
                "application/json",
            )
        else:
            self._send(404, "Introuvable.")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/pixels":
            try:
                length = int(self.headers.get("Content-Length", 0))
                label = json.loads(self.rfile.read(length) or b"{}").get("label", "Sans nom")
            except Exception:
                label = "Sans nom"
            token = create_pixel(label)
            self._send(
                201,
                json.dumps({"token": token, "url": f"{BASE_URL}/p/{token}.png"}),
                "application/json",
            )
        else:
            self._send(404, "Introuvable.")


# ---------------------------------------------------------------- interface en ligne de commande

def cmd_new(label):
    token = create_pixel(label)
    print(f"Pixel « {label} » créé.")
    print(f"URL : {BASE_URL}/p/{token}.png")


def cmd_list():
    con = db()
    rows = con.execute(
        "SELECT p.label, p.token, p.created_at, COUNT(o.id) "
        "FROM pixels p LEFT JOIN opens o ON o.pixel_id = p.id "
        "GROUP BY p.id ORDER BY p.id DESC"
    ).fetchall()
    con.close()
    if not rows:
        print("Aucun pixel.")
        return
    for label, token, created, n in rows:
        print(f"- {label} | {fmt(created)} | {n} ouverture(s)")
        print(f"  {BASE_URL}/p/{token}.png")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "new":
        cmd_new(" ".join(sys.argv[2:]) or "Sans nom")
    elif len(sys.argv) >= 2 and sys.argv[1] == "list":
        cmd_list()
    else:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
        print(f"Pixel tracker en écoute sur le port {PORT} (BASE_URL={BASE_URL})")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
