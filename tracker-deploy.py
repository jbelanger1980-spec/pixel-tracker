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
import hashlib
import html
import json
import re
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

# GIF animé surprise : le doigt grossit jusqu'à remplir l'image, puis la
# mention « Ce courriel est suivi. » apparaît. Servi aux URL de pixels
# (affiché en 1x1 dans le courriel : invisible, mais le fichier contient
# la surprise pour qui l'extrait). Conservé : l'ancien PNG 1x1 transparent
# comme repli si le GIF est indisponible.
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
SURPRISE_GIF = base64.b64decode(
    "R0lGODlhLAG+AIUAAP///////v/+/v7+/v78+v77+v/59f359/359v359f/56P349f728P328v328f318P307fzx6fzw5//w3/zv5v/v3v/u3f/t3P7s2//r2//r2v3r3/rq4f/o1/zn2vzn1/rp3vrn3frm1/np3/np3vjn2/nm2v/l0vnl2vnk1/ni0vjl2Pvh0fnh0vjh0v/fzvrg0fjfzvffz/bfz/fezvbez/bezvXez/fdzfbdzvXdzfXcz/XVxO/Lue7KuQAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAFgAAACwAAAAALAG+AAAI/wABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDihxJsqTJkyhTqlzJsqXLlzBjypxJs6bNmzhz6tzJs6fPn0CDCh1KtKjRo0iTKl3KtKnTp1CjSp1KtapVgwEAcPhAAICAq2DDdsyKYgICsWjTWgwQwASGs2rjynWI4kKCr3Pz6hX4gMIKDQcAZN1LGO3XEgpmwGBQoLBjsTt4pMBRg4ULCI0fa5Zq4EQPFzhi0KChAITXzaiXZpXwwocKHKNtZAhxOrVto1kpvOjxenQODSRq3x4+tEEHHTJG07hhgYNg4tCFlqhgw7cMCw6iawdaQIQGHTRYTP8Ysb28zwUbWsTwEAHAAPPw48ufT7++/fv48+vfz7+///8ABijggAQWaOCBCCao4IIMNujggxBGKOGEFFZo4YUYZqjhhhx26OGHIIYo4ogklmjiiSimqOKKLLbo4oswxijjjDTWaOONOOao44489ujjj0AGKeSQRBZp5JFIJqnkkkw26eSTUEYp5ZRUVmnllVhmqeWWXHbp5ZdghinmmGSWaeaZaKap5ppstunmm3DGKeecdNZp55145qnnnnz26eefgAYq6KCEFmrooYgmquiijDbq6KOQRirppJRWaumlmGaq6aacdurpp6CGKuqopJZq6qmopqrqqqy26uqrsMYgKuustNZq66245qrrrrz26uuvwAYr7LDEFmvsscjSGBAAIfkEARYAPQAsigAMABgAHACF///////+//7+/v7+/v38/vz7/vv5/vn2/ffz/fXw/PTv/PTu/PPp//Lh+/Dq+/Dp++7l//De/+/e/+7d/+3c/+3b/+zb++3k+uzj/uva/+nY/OnY/+fX/efX/ebV++fZ+efc+ebb/OXX+uXW+uTV+uTU+eXY/OPT+OLT+ODQ+N/P99/P9t/P9t/O+N7O997P997O9t7Q9t7P9t7O9t3O9t3N9d3N9tzN89PD7ci36byp5LSg5LOfAAAAAAAAAAAACP8AewgcOBCAgQ8dQhAAEICgw4c9AEBo0CJCgh4DIGocAADDBBkUFvQQoBFixgsSQIokWdIhR5QqAbBsKRDAy5QhR9IkeLNHSJk7awLoiHMBUAAtkRIoIABChJgkkWpsaGDEBhMgMqwIOSBqyQABHjS4caKGCxYTFAyNSHOBhBUwYPSQkcHBggUNdT5EEALHhhpx5bqIoaEBCIgkDYhwoaME4MAwUtBQ4QKEhQcESYrNsYPE48CPa3DQwOEAxoEgInD2DLl1jRYWGOgtsKLD6s+t47KoO7IhghMobueGzMKCg949fgfvjDt38eMCqL7wkIMH6+G6c84MkeEGDhXYA9tq6HBRYMMEGl6kCB+3RooXBnQGIGlCww32MGRwMCEwo04EJaDQXGszWFAeQQ09UEEKM2A3gwQh9JBXZj1g0MALNkBWAw0zRPBBAac9NMAAGHjAAXhxnaBBCReAuFMCIMQA3gsfQGCahAQFBAAh+QQBFgBAACyEAAwAJQAwAIX///////7+/////v7//v3//vz+/v7//fz+/f3++/r++vf9+fX99/L89O7+8uX88On/8N//797/7t3/7dz77uX/69r66+L/6dj+6Nj76d366d/66d756d7959f55tn95NP65dX65Nr65NT55Nf74tL64tX64dH64dD44tP64ND44NH438/34dL339D239H238/238743s/33s723tD23s/23s713s733c323c723c313c3y1sbmsp7gqpfgqpXep5EI/wCBCBxIsCCQBiVStLBwYIDBhxAhMkhBIkeOCBQAGIjI8aEBABoqvJCRg4QKBEAcdlyZEsAGCTRk1DAxg0BKlisHuIQpk6ZNlTgj6nwZc2bNm0GF7izqE2nShw6J9jwK9GnBoTyN/rRKEIBXrEypch3oFQDYqVvHkj2r1SwQAGPLggXStmpQuGXNDiBK16dZr0/xavwIgAPMvjX/AoYbNAGFDBksIOAQgQZiAorxsnRIwAMEDBgcaOAwwcXlzG83A2HQocWLFylmtEghsO2BsqlxNoAwUmaMFQPb5s3dkQCC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"
)


def gif_for_token(token):
    """GIF surprise avec un commentaire unique par token : chaque courriel a
    des octets différents (anti-détection par signature), visuel identique.

    Le commentaire est inséré juste avant le trailer (0x3B), seul
    emplacement sûr : placé ailleurs (ex. entre l'en-tête et la palette),
    certains décodeurs (Chrome, téléphones) affichent un rectangle blanc.
    Correctif du 2026-09-23 : carré blanc constaté par Julien sur son S25.
    """
    nonce = hashlib.sha256(("surprise-" + token).encode("utf-8")).hexdigest()[:16]
    ext = b"\x21\xFE" + bytes([len(nonce)]) + nonce.encode("ascii") + b"\x00"
    assert SURPRISE_GIF[-1:] == b"\x3B", "trailer GIF introuvable"
    return SURPRISE_GIF[:-1] + ext + b"\x3B"


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
    con.execute(
        "CREATE TABLE IF NOT EXISTS ip_cache("
        "ip TEXT PRIMARY KEY, city TEXT, region TEXT, country TEXT, "
        "org TEXT, updated_at TEXT NOT NULL)"
    )
    # Migration 2026-09-23 : distingue les chargements du pixel caché
    # (kind='pixel') des clics sur le GIF visible (kind='click').
    try:
        con.execute("ALTER TABLE opens ADD COLUMN kind TEXT NOT NULL DEFAULT 'pixel'")
    except sqlite3.OperationalError:
        pass  # colonne déjà présente
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


def record_open(token, ip, user_agent, kind="pixel"):
    con = db()
    row = con.execute("SELECT id FROM pixels WHERE token=?", (token,)).fetchone()
    if row:
        con.execute(
            "INSERT INTO opens(pixel_id, opened_at, ip, user_agent, kind) VALUES(?,?,?,?,?)",
            (row[0], datetime.now(timezone.utc).isoformat(), ip, (user_agent or "")[:300], kind),
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


# Plages d'adresses des serveurs d'images de Google (proxy Gmail).
GOOGLE_PREFIXES = (
    "74.125.", "66.102.", "64.233.", "72.14.", "209.85.", "173.194.",
    "108.177.", "216.58.", "172.217.", "142.250.", "108.59.",
)

# Modèle du téléphone de Julien (Galaxy S25 Ultra) : quand il apparaît dans
# le client, c'est lui qui a consulté le courriel. Pas besoin de comparer
# les adresses IP (la sienne peut changer).
JULIEN_PHONE_MARKER = "SM-S938W"

# Robots / scans de sécurité : quand un filtre antispam ou un scanner
# télécharge l'image, on l'affiche comme un scan, pas comme une vraie lecture.
BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|mediapartners|baidu|yandex|sogou|exabot|"
    r"facebot|ia_archiver|scan|proofpoint|barracuda|mimecast|fireeye|"
    r"sophos|mcafee|urldefense|defender|antivirus|threat|phish",
    re.I,
)


def geo_place(ip):
    """'Ville, Pays' depuis le cache local, ou '' si le lieu est inconnu."""
    if not ip:
        return ""
    try:
        con = db()
        row = con.execute(
            "SELECT city, country FROM ip_cache WHERE ip=?", (ip,)
        ).fetchone()
        con.close()
    except Exception:
        return ""
    if not row:
        return ""
    return ", ".join(p for p in (row[0], row[1]) if p)


def classify_open(ip, ua):
    """Classe une ouverture en langage clair.

    Retourne (code, qui, lieu) :
      - ("moi", "Ouvert par ton téléphone S25", "")
      - ("google", "Chargé via Google (Gmail)", "Serveurs de Google")
      - ("robot", "Scan de sécurité détecté", "Ville, Pays" ou "")
      - ("externe", "Ouvert par quelqu'un d'autre", "Ville, Pays" ou "Lieu à déterminer")
    """
    ua = ua or ""
    ip = ip or ""
    if JULIEN_PHONE_MARKER in ua:
        return ("moi", "Ouvert par ton téléphone S25", "")
    if BOT_RE.search(ua):
        return ("robot", "Scan de sécurité détecté",
                geo_place(ip) or "")
    if ("GoogleImageProxy" in ua or "ggpht.com" in ua
            or ip.startswith(GOOGLE_PREFIXES)):
        return ("google", "Chargé via Google (Gmail)", "Serveurs de Google")
    return ("externe", "Ouvert par quelqu'un d'autre",
            geo_place(ip) or "Lieu à déterminer")


# ---------------------------------------------------------------- tableau de bord

def dashboard():
    con = db()
    pixels = con.execute(
        "SELECT p.id, p.token, p.label, p.created_at, COUNT(o.id), "
        "SUM(CASE WHEN o.kind='click' THEN 1 ELSE 0 END) "
        "FROM pixels p LEFT JOIN opens o ON o.pixel_id = p.id "
        "GROUP BY p.id ORDER BY p.id DESC"
    ).fetchall()
    opens = con.execute(
        "SELECT o.opened_at, p.label, o.ip, o.user_agent, o.kind "
        "FROM opens o JOIN pixels p ON p.id = o.pixel_id "
        "ORDER BY o.id DESC LIMIT 100"
    ).fetchall()
    con.close()

    rows = []
    for _id, token, label, created, n, nclicks in pixels:
        url = f"{BASE_URL}/p/{token}.gif"
        rows.append(
            f"<tr><td>{esc(label)}</td><td>{fmt(created)}</td>"
            f"<td><strong>{n}</strong></td><td><strong>{nclicks or 0}</strong></td>"
            f'<td><code>{esc(url)}</code> '
            f"<button onclick=\"navigator.clipboard.writeText('{esc(url)}')\">copier</button></td></tr>"
        )
    orows = []
    for ts, label, ip, ua, evkind in opens:
        ckind, qui, lieu = classify_open(ip, ua)
        badge_clic = (' <span class="badge clic">Clic sur le GIF 🎯</span>'
                      if evkind == "click" else "")
        orows.append(
            f'<tr data-ip="{esc(ip)}" data-ua="{esc((ua or "")[:120])}">'
            f"<td>{fmt(ts)}</td><td>{esc(label)}</td>"
            f'<td><span class="badge {ckind}">{esc(qui)}</span>{badge_clic}</td>'
            f"<td>{esc(lieu)}</td></tr>"
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pixel tracker</title>
<link rel="icon" type="image/png" href="/icone.png">
<link rel="apple-touch-icon" href="/icone.png">
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.88rem;vertical-align:top}}
th{{background:#f2f2f2}}code{{word-break:break-all;font-size:.8rem}}
button{{cursor:pointer}}
.badge{{display:inline-block;padding:.15rem .55rem;border-radius:1rem;font-size:.8rem;font-weight:600;white-space:nowrap}}
.badge.moi{{background:#e6f4ea;color:#137333}}
.badge.google{{background:#fef7e0;color:#a15c00}}
.badge.robot{{background:#e8f0fe;color:#1a56db}}
.badge.externe{{background:#fce8e6;color:#a50e0e}}
.badge.clic{{background:#f3e8fd;color:#7b1fa2}}
.legende p{{margin:.3rem 0;font-size:.88rem}}
</style></head><body>
<h1>&#x1f4e1; Suivi des ouvertures de courriels</h1>
<h2>Pixels ({len(pixels)})</h2>
<table><tr><th>Étiquette</th><th>Créé le</th><th>Ouvertures</th><th>Clics sur le GIF</th><th>URL du pixel</th></tr>
{"".join(rows) or "<tr><td colspan=4>Aucun pixel. Crée-en un avec : <code>python3 tracker.py new &quot;Nom&quot;</code></td></tr>"}
</table>
<h2>Ouvertures récentes</h2>
<table><tr><th>Date (heure de Montréal)</th><th>Courriel</th><th>Qui</th><th>Lieu</th></tr>
{"".join(orows) or "<tr><td colspan=4>Aucune ouverture enregistrée pour l'instant.</td></tr>"}
</table>
<div class="legende">
<p><span class="badge moi">Ouvert par ton téléphone S25</span> : c'était toi qui consultais le courriel.</p>
<p><span class="badge google">Chargé via Google (Gmail)</span> : l'image est passée par les serveurs de Google. Impossible de confirmer qui l'a ouverte.</p>
<p><span class="badge robot">Scan de sécurité détecté</span> : un robot ou un filtre antispam a téléchargé l'image. Ce n'est pas une vraie lecture.</p>
<p><span class="badge externe">Ouvert par quelqu'un d'autre</span> : une vraie ouverture depuis une autre connexion. Le lieu s'affiche quand il est connu.</p>
</div>
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
        if (path.startswith("/p/") and (path.endswith(".png") or path.endswith(".gif"))) or (
            path.startswith("/c/") and path.endswith(".gif")
        ):
            # /p/ = pixel caché (chargement automatique de l'image).
            # /c/ = clic humain sur le GIF visible (même surprise affichée,
            #       mais enregistré comme "click" dans le tableau de bord).
            # Les deux préfixes font 3 caractères, donc path[3:-4] convient.
            is_click = path.startswith("/c/")
            token = path[3:-4]
            record_open(token, client_ip(headers), headers.get("user-agent", ""),
                        kind="click" if is_click else "pixel")
            try:
                body_gif = gif_for_token(token)
            except Exception:
                body_gif = PIXEL_PNG
            return (
                200,
                [
                    ("Content-Type", "image/gif"),
                    ("Cache-Control", "no-store, no-cache, must-revalidate"),
                    ("Pragma", "no-cache"),
                    ("Expires", "0"),
                ],
                body_gif,
            )
        elif path == "/icone.png":
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "icone.png")
            if os.path.exists(icon_path):
                with open(icon_path, "rb") as f:
                    return 200, [("Content-Type", "image/png"),
                                 ("Cache-Control", "max-age=86400")], f.read()
            return text(404, "Introuvable.")
        elif path in ("/", "/dashboard"):
            if DASH_TOKEN and qs.get("token", [""])[0] != DASH_TOKEN:
                return text(403, "Accès refusé : ?token= requis.")
            return text(200, dashboard())
        elif path == "/api/pixels":
            con = db()
            rows = con.execute(
                "SELECT p.token, p.label, p.created_at, COUNT(o.id) "
                "FROM pixels p LEFT JOIN opens o ON o.pixel_id = p.id "
                "GROUP BY p.id ORDER BY p.id DESC"
            ).fetchall()
            con.close()
            return (
                200,
                [("Content-Type", "application/json")],
                json.dumps(
                    [{"token": t, "label": l, "created_at": c, "opens": n,
                      "url": f"{BASE_URL}/p/{t}.gif",
                      "click_url": f"{BASE_URL}/c/{t}.gif"} for t, l, c, n in rows]
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
                    {"token": token, "url": f"{BASE_URL}/p/{token}.gif",
                     "click_url": f"{BASE_URL}/c/{token}.gif"}
                ).encode("utf-8"),
            )
        elif parsed.path == "/api/ipinfo":
            # Enrichissement du lieu d'une IP (appelé par la surveillance,
            # jamais par un pixel). Authentifié par ?token= comme le tableau.
            if DASH_TOKEN and qs.get("token", [""])[0] != DASH_TOKEN:
                return text(403, "Accès refusé : ?token= requis.")
            try:
                data = json.loads(body or b"{}")
            except Exception:
                return text(400, "Requête invalide.")
            ip = str(data.get("ip", "")).strip()
            if not ip:
                return text(400, "IP manquante.")
            con = db()
            con.execute(
                "INSERT INTO ip_cache(ip, city, region, country, org, updated_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(ip) DO UPDATE SET city=excluded.city,"
                " region=excluded.region, country=excluded.country,"
                " org=excluded.org, updated_at=excluded.updated_at",
                (ip, data.get("city"), data.get("region"),
                 data.get("country"), data.get("org"),
                 datetime.now(timezone.utc).isoformat()),
            )
            con.commit()
            con.close()
            return 200, [("Content-Type", "application/json")], b'{"ok":true}'
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
    400: "Bad Request",
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
    print(f"URL : {BASE_URL}/p/{token}.gif")


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
        print(f"  {BASE_URL}/p/{token}.gif")


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
