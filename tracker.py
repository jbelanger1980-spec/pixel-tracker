#!/usr/bin/env python3
"""
Pixel de suivi d'ouverture de courriels — mini-clone de icollector.ai.

Principe : chaque pixel est une URL unique qui sert une image invisible de
1x1 pixel. Quand le destinataire ouvre le courriel, son client charge
l'image et le serveur enregistre l'ouverture (date, IP, client).

Usage :
  python3 tracker.py new "Étiquette"   -> crée un pixel, affiche son URL
  python3 tracker.py list              -> liste les pixels et leurs stats
  python3 tracker.py                   -> lance le serveur web local

Déploiement (PythonAnywhere, WSGI) : le fichier expose aussi un appelable
WSGI nommé ``application``. Voir README.md, section PythonAnywhere.

Variables d'environnement :
  PORT        port d'écoute en local (défaut : 8000)
  BASE_URL    URL publique du serveur, ex. https://xxx.pythonanywhere.com
              (obligatoire en pratique : sans URL publique, personne
              d'autre que toi ne peut charger le pixel)
  DB_PATH     chemin du fichier SQLite (défaut : pixels.db à côté du script)
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
            (row[0], datetime.now(timezone.utc).isoformat(), ip, (user_agent or "")[:300]),
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


def client_ip(headers):
    """headers : dict à clés minuscules. Prend X-Forwarded-For puis l'IP directe."""
    fwd = headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return headers.get("remote-addr", "")


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


# ---------------------------------------------------------------- coeur applicatif (serveur local ET WSGI)

def handle_request(method, full_path, headers, body):
    """Traite une requête.

    method     : "GET", "POST", ...
    full_path  : chemin + éventuelle chaîne de requête, ex. "/?token=abc"
    headers    : dict à clés minuscules
    body       : bytes du corps (POST)

    Retourne (code_statut, [(nom, valeur), ...], corps_en_bytes).
    """
    parsed = urlparse(full_path)
    path = parsed.path
    qs = parse_qs(parsed.query)

    def text(code, s, ctype="text/html; charset=utf-8"):
        data = s.encode("utf-8")
        return code, [("Content-Type", ctype)], data

    if method == "GET":
        if path.startswith("/p/") and path.endswith(".png"):
            record_open(path[3:-4], client_ip(headers), headers.get("user-agent", ""))
            return (
                200,
                [
                    ("Content-Type", "image/png"),
                    ("Cache-Control", "no-store, no-cache, must-revalidate"),
                    ("Pragma", "no-cache"),
                    ("Expires", "0"),
                ],
                PIXEL_PNG,
            )
        elif path in ("/", "/dashboard"):
            if DASH_TOKEN and qs.get("token", [""])[0] != DASH_TOKEN:
                return text(403, "Accès refusé : ?token= requis.")
            return text(200, dashboard())
        elif path == "/api/pixels":
            con = db()
            rows = con.execute(
                "SELECT token, label, created_at FROM pixels ORDER BY id DESC"
            ).fetchall()
            con.close()
            return (
                200,
                [("Content-Type", "application/json")],
                json.dumps(
                    [{"token": t, "label": l, "created_at": c,
                      "url": f"{BASE_URL}/p/{t}.png"} for t, l, c in rows]
                ).encode("utf-8"),
            )
        return text(404, "Introuvable.")

    if method == "POST":
        if parsed.path == "/api/pixels":
            try:
                label = json.loads(body or b"{}").get("label", "Sans nom")
            except Exception:
                label = "Sans nom"
            token = create_pixel(label)
            return (
                201,
                [("Content-Type", "application/json")],
                json.dumps(
                    {"token": token, "url": f"{BASE_URL}/p/{token}.png"}
                ).encode("utf-8"),
            )
        return text(404, "Introuvable.")

    return text(405, "Méthode non prise en charge.")


# ---------------------------------------------------------------- adaptateur serveur local (http.server)

class Handler(BaseHTTPRequestHandler):
    server_version = "PixelTracker/1.0"

    def log_message(self, *args):  # silencieux
        pass

    def _respond(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        headers = {k.lower(): v for k, v in self.headers.items()}
        headers.setdefault("remote-addr", self.client_address[0])
        status, resp_headers, resp_body = handle_request(
            self.command, self.path, headers, body
        )
        self.send_response(status)
        for name, value in resp_headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self):
        self._respond()

    def do_POST(self):
        self._respond()


# ---------------------------------------------------------------- adaptateur WSGI (PythonAnywhere et autres)

_STATUS_PHRASES = {
    200: "OK",
    201: "Created",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
}


def application(environ, start_response):
    """Point d'entrée WSGI. Exemple de fichier WSGI PythonAnywhere :

    import os, sys
    os.environ["BASE_URL"] = "https://<user>.pythonanywhere.com"
    os.environ["DASH_TOKEN"] = "<jeton-secret>"
    os.environ["DB_PATH"] = "/home/<user>/pixels.db"
    sys.path.insert(0, "/home/<user>/pixel-tracker")
    from tracker import application
    """
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"
    qs = environ.get("QUERY_STRING", "")
    full_path = path + ("?" + qs if qs else "")

    headers = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers[key[5:].replace("_", "-").lower()] = value
    if environ.get("CONTENT_TYPE"):
        headers["content-type"] = environ["CONTENT_TYPE"]
    if environ.get("REMOTE_ADDR"):
        headers.setdefault("remote-addr", environ["REMOTE_ADDR"])

    try:
        length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    except (TypeError, ValueError):
        length = 0
    body = environ["wsgi.input"].read(length) if length > 0 else b""

    status, resp_headers, resp_body = handle_request(method, full_path, headers, body)
    start_response(
        f"{status} {_STATUS_PHRASES.get(status, '')}".strip(), resp_headers
    )
    return [resp_body]


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
