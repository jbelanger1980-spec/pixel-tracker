# Pixel tracker

Mini-clone de icollector.ai : un serveur qui génère des pixels de suivi
invisibles (1x1 transparent) pour savoir quand tes courriels sont ouverts.
Python standard seulement, aucune dépendance à installer. Les données sont
stockées dans `pixels.db` (SQLite).

## Démarrage rapide

```bash
cd ~/workspace/pixel-tracker
python3 tracker.py            # lance le serveur sur le port 8000
```

Ouvre ensuite http://localhost:8000 dans ton navigateur : c'est le tableau
de bord (liste des pixels, compteur d'ouvertures, historique détaillé).

## Créer un pixel

```bash
python3 tracker.py new "Prime500 - mise en demeure"
# Affiche : URL : http://localhost:8000/p/xxxx.png
```

Chaque pixel a une URL unique : utilise un pixel différent par courriel ou
par destinataire pour savoir exactement lequel a été ouvert.

## Glisser le pixel dans un courriel Gmail

1. Rédige ton message dans Gmail.
2. Clique sur l'icône **image** dans la barre d'outils, onglet
   **Adresse Web (URL)**.
3. Colle l'URL du pixel, insère-la, puis choisis la taille **Petite**.
4. L'image est un carré transparent d'un pixel : invisible pour le
   destinataire, mais son client la chargera à l'ouverture.

## Le mettre en ligne (obligatoire pour un vrai usage)

Tant que le serveur tourne en `localhost`, seul ton propre ordinateur peut
charger le pixel : ça sert juste à tester. Pour que le suivi fonctionne avec
de vrais destinataires, le serveur doit avoir une **URL publique**.

**Option A — test rapide (gratuit, temporaire) :** un tunnel Cloudflare.

```bash
# Sur ton PC Linux :
cloudflared tunnel --url http://localhost:8000
# Cloudflare affiche une URL du type https://quelque-chose.trycloudflare.com
BASE_URL=https://quelque-chose.trycloudflare.com python3 tracker.py
```

Recrée ensuite tes pixels : leurs URL utiliseront la nouvelle adresse
publique. L'URL change à chaque redémarrage du tunnel : c'est pour tester,
pas pour du permanent.

**Option B — permanent :** déploie `tracker.py` sur un serveur à toi
(VPS, Raspberry Pi exposé, Render, Fly.io...). Exemple avec un VPS :

```bash
BASE_URL=https://pixels.ton-domaine.com PORT=8000 \
DASH_TOKEN=un-mot-de-passe-solide python3 tracker.py
```

Puis configure un reverse proxy (nginx, Caddy) avec HTTPS devant.

## Protéger le tableau de bord

Si le serveur est exposé sur Internet, définis `DASH_TOKEN` : le tableau de
bord exigera alors `?token=...` dans l'URL. Le pixel lui-même (`/p/...`)
doit rester public, sinon le suivi ne fonctionne pas.

## Limites honnêtes

- Si le destinataire bloque les images, aucune ouverture n'est enregistrée.
- Les antispams et serveurs de courriel ouvrent parfois les messages
  automatiquement : une « ouverture » peut venir d'un robot, pas d'un humain.
- Gmail charge les images via son propre proxy : tu verras l'ouverture,
  mais l'adresse IP affichée sera celle de Google, pas celle du destinataire.
- Le suivi d'ouverture de tes propres courriels est une pratique courante
  (c'est ce que font Mailtrack, Mailchimp et compagnie), mais reste discret
  par principe : un pixel par message, rien de plus.

## Déploiement clé en main (plus rien à garder allumé)

Les fichiers `Dockerfile`, `render.yaml` et `fly.toml` sont prêts. Le principe
est le même des deux côtés : le tracker tourne 24/7 chez l'hébergeur, avec un
disque persistant pour la base SQLite.

**Option 1 — Render (le plus simple, mais avec une réserve).**
1. Mets le dossier sur GitHub (`git init`, commit, push).
2. Sur https://dashboard.render.com : New → Blueprint → choisis ton dépôt.
3. Render crée le service, le disque et un `DASH_TOKEN` aléatoire (visible
   ensuite dans les variables d'environnement du service).
4. Vérifie l'URL publique (ex. `https://pixel-tracker.onrender.com`) et
   ajuste `BASE_URL` dans les variables d'environnement si besoin.
5. Recrée tes pixels : leurs URL utiliseront la nouvelle adresse.

Réserve honnête : sur l'offre gratuite, Render met le service en veille
après ~15 minutes sans trafic. Un pixel demandé pendant la veille peut
rater l'ouverture (l'image met trop de temps à répondre). Pour du suivi
fiable, soit tu passes au plan payant, soit tu prends l'option 2.

**Option 2 — Fly.io (gratuit dans la limite de l'offre, reste éveillé).**
1. Installe `flyctl` et connecte-toi : `fly auth login`.
2. Personnalise le nom d'app dans `fly.toml` (doit être unique).
3. Crée le volume persistant : `fly volumes create pixel_data --region yul --size 1`
4. Déploie : `fly deploy`
5. Définis l'URL publique : `fly secrets set BASE_URL=https://<ton-app>.fly.dev`
   puis `fly deploy` à nouveau pour l'appliquer.
6. Recrée tes pixels avec la nouvelle adresse.

Ici `auto_stop_machines = false` et `min_machines_running = 1` gardent le
service éveillé en permanence. Vérifie les conditions de l'offre gratuite au
moment de l'inscription (une carte bancaire est généralement demandée même
pour le palier gratuit).

Dans les deux cas, le tableau de bord reste protégé par `DASH_TOKEN`
(`?token=...` dans l'URL), et une seule instance tourne à la fois (SQLite
n'aime pas le multi-instance).

## Sur Android avec Termux

1. Installe Termux depuis F-Droid (la version du Play Store est abandonnée,
   prends celle de F-Droid ou GitHub).
2. Récupère `tracker.py` sur ton téléphone (fichier joint à la conversation).
3. Dans Termux :
   ```bash
   pkg install python
   termux-setup-storage
   cp ~/storage/downloads/tracker.py ~/
   python ~/tracker.py
   ```
   Le tableau de bord est visible dans le navigateur du téléphone à
   http://127.0.0.1:8000.
4. Pour l'URL publique :
   ```bash
   pkg install cloudflared
   cloudflared tunnel --url http://127.0.0.1:8000
   ```
   Cloudflare affiche une adresse `https://xxx.trycloudflare.com`. Relance
   ensuite avec
   `BASE_URL=https://xxx.trycloudflare.com python ~/tracker.py`
   et recrée tes pixels pour qu'ils utilisent cette adresse.
5. Pour que ça survive écran éteint : lance `termux-wake-lock`, et dans les
   paramètres Android va dans Applis → Termux → Batterie → « Sans
   restrictions ».

Limites honnêtes : le téléphone doit rester allumé avec Termux actif, et
Android peut quand même tuer le processus malgré ces réglages. L'URL
trycloudflare change à chaque redémarrage du tunnel : un pixel créé avec
l'ancienne adresse ne fonctionnera plus, donc le tunnel doit rester en vie
au moins jusqu'à ce que le destinataire ouvre le courriel. Un tunnel nommé
(compte Cloudflare + nom de domaine) donne une adresse stable. Pour un suivi
fiable sur plusieurs jours, un PC allumé en permanence ou un petit VPS reste
plus solide que le téléphone.

## API (optionnel)

- `GET /api/pixels` — liste les pixels en JSON.
- `POST /api/pixels` avec `{"label": "..."}` — crée un pixel, retourne son URL.
