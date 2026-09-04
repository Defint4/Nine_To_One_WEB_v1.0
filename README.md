# Nine to One

Jeu de cartes multijoueur en temps réel (2 à 5 joueurs), pensé pour le téléphone : on entre
un pseudo, on crée une table, on partage son code, et on joue. Des bots à trois niveaux
complètent les tables ; le niveau Difficile est un réseau entraîné par auto-jeu, avec une
recherche sur les cartes cachées au moment de jouer.

- Frontend : Next.js 16 (PWA mobile), servi par `next start` sur le port 3003.
- Backend : FastAPI + WebSocket, PostgreSQL pour les profils, tables en mémoire (un seul
  processus). Port 8003.
- Bots : numpy pur, aucun torch en production (poids exportés dans `backend/app/*.npz`).
- Production : https://9to1.matthieuguiot.dev

```
backend/    API, moteur de règles (backend/app/engine, 68 tests), bots (app/bots.py, app/botbrain.py)
frontend/   application Next.js
deploy/     services systemd + configuration nginx
ml/         entraînement des bots (torch, hors production)
docs/       règles officielles du jeu
```

---

## Déploiement en production — `9to1.matthieuguiot.dev`

Même VPS que `portfolio-2026`, `concreteFencing` et `invoice_Maker` (Ubuntu 24.04,
utilisateur `matthieu`, nginx + certbot + PostgreSQL + uv + Node 22 + pnpm déjà installés).

| | |
|---|---|
| Dossier | `/var/www/9to1` |
| Services | `9to1-backend` (port 8003) · `9to1-frontend` (port 3003) |
| Ports déjà pris | 8000/3000 portfolio · 8001/3001 concrete · 8002/3002 invoice |
| Base | rôle et base PostgreSQL `ninetoone` |

### 0. DNS

Chez Cloudflare (zone `matthieuguiot.dev`), un enregistrement **A** :

```
9to1.matthieuguiot.dev  →  IP du VPS
```

En « DNS only » (nuage gris) le temps de générer le certificat.

### 1. PostgreSQL — rôle et base dédiés

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE ninetoone WITH LOGIN PASSWORD 'MOT_DE_PASSE_FORT';
CREATE DATABASE ninetoone OWNER ninetoone;
\q
```

### 2. Récupérer le code

Une deploy key GitHub est scopée à un seul repo : en créer une dédiée.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_9to1 -C "vps-9to1-deploy" -N ""
cat ~/.ssh/github_9to1.pub
```

Coller la clé publique dans GitHub → repo de ce projet → *Settings → Deploy keys* (lecture
seule). Puis :

```bash
cat >> ~/.ssh/config << 'EOF'

Host github-9to1
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_9to1
    IdentitiesOnly yes
EOF

sudo mkdir -p /var/www/9to1
sudo chown matthieu:www-data /var/www/9to1
git clone github-9to1:Defint4/Nine_To_One_WEB_v1.0.git /var/www/9to1
chmod +x /var/www/9to1/deploy.sh
```

### 3. Backend

```bash
cd /var/www/9to1/backend
cp .env.example .env
nano .env
```

À renseigner :

```
DATABASE_URL=postgresql+asyncpg://ninetoone:MOT_DE_PASSE_FORT@localhost:5432/ninetoone
ENVIRONMENT=production
CORS_ORIGINS=["https://9to1.matthieuguiot.dev"]
JWT_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
BOT_TIME_BUDGET=0.5
BOT_THREADS=1
```

`JWT_SECRET` est obligatoire : l'API refuse de démarrer s'il fait moins de 32 caractères.
`BOT_TIME_BUDGET` / `BOT_THREADS` bornent le CPU consommé par le bot Difficile (voir
« Les bots » plus bas).

```bash
uv sync
uv run alembic upgrade head
mkdir -p logs

# Test rapide (puis Ctrl+C)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8003
curl http://127.0.0.1:8003/api/health      # {"status":"ok"}
```

`uv sync` construit `.venv`. Le service systemd lance ensuite `.venv/bin/uvicorn`
directement, sans passer par `uv` : le durcissement du service interdit d'écrire dans
`~/.cache/uv`. Ne pas remplacer `ExecStart` par `uv run`, le service ne démarrerait plus.

Un seul worker uvicorn, toujours : les tables de jeu vivent dans la mémoire du processus.
Ne jamais ajouter `--workers`.

### 4. Frontend

L'adresse de l'API est embarquée dans le build (`NEXT_PUBLIC_API_URL`) : REST et
WebSocket passent par nginx sur le même domaine.

```bash
cd /var/www/9to1/frontend
cp .env.example .env.production
pnpm install --frozen-lockfile
pnpm build
```

### 5. Services systemd

```bash
sudo cp /var/www/9to1/deploy/9to1-backend.service /etc/systemd/system/
sudo cp /var/www/9to1/deploy/9to1-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 9to1-backend 9to1-frontend
sudo systemctl status 9to1-backend 9to1-frontend
```

### 6. Nginx + HTTPS

```bash
sudo cp /var/www/9to1/deploy/nginx-9to1.conf /etc/nginx/sites-available/9to1
sudo ln -s /etc/nginx/sites-available/9to1 /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d 9to1.matthieuguiot.dev
```

La config nginx garde le WebSocket de partie ouvert (`proxy_read_timeout 3600s` sur
`/api/`) : sans cela, nginx couperait la connexion après 60 s de silence en lobby.

### 7. Vérifications

```bash
curl https://9to1.matthieuguiot.dev/api/health
sudo systemctl is-enabled 9to1-backend 9to1-frontend
sudo journalctl -u 9to1-backend -n 30 --no-pager
```

Dans le navigateur, sur téléphone : entrer un pseudo, créer une table, ajouter un bot
Difficile depuis le lobby (bouton « + » à droite des places libres), se déclarer prêt et
jouer une manche. Une fois le certificat en place, repasser l'entrée DNS en proxy
Cloudflare (nuage orange) si souhaité : le WebSocket passe sans réglage particulier.

### 8. Mises à jour

```bash
cd /var/www/9to1
./deploy.sh
```

`git pull` → `uv sync` + migrations → `pnpm install` + build → restart des deux services.

### Commandes utiles

```bash
sudo journalctl -u 9to1-backend -f
sudo journalctl -u 9to1-frontend -f
sudo systemctl restart 9to1-backend 9to1-frontend
sudo -u postgres pg_dump ninetoone | gzip > ~/ninetoone-$(date +%F).sql.gz   # sauvegarde
```

---

## Les bots

Trois niveaux, ajoutés par le créateur de la table depuis le lobby :

| Niveau | Politique | Coût serveur |
|---|---|---|
| Facile | coup légal au hasard, une carte à la fois, n'enchaîne jamais | nul |
| Normal | heuristique « économe » : plus petite carte normale, multiples, garde ses 2 et 10, enchaîne | nul |
| Difficile | réseau (MLP 223→512→512→256, numpy) + recherche sur les cartes cachées | 1 cœur pendant `BOT_TIME_BUDGET` s par coup |

Le bot Difficile lit uniquement ce qu'un joueur verrait à sa place (sa vue + les
événements publics) : il ne triche pas. Il réfléchit dans un thread séparé (au plus
`BOT_THREADS` réflexions à la fois, chacune bornée à `BOT_TIME_BUDGET` secondes), la boucle
réseau continue de servir les autres tables pendant ce temps. Mémoire : ~75 Mo pour le
processus backend, poids compris. Aucune dépendance torch en production.

Chaque manche jouée contre un bot est journalisée dans `backend/logs/games.jsonl`
(`GAMES_LOG_PATH`, vide pour désactiver). Bilan : `python3 ml/analyze_games.py`.

Les bots ne comptent pas dans les statistiques des joueurs, suivent la revanche et se
mettent prêts tout seuls.

---

## Développement local

```bash
docker compose up -d                       # PostgreSQL sur 127.0.0.1:5435

cd backend
cp .env.example .env                       # DATABASE_URL → port 5435, ENVIRONMENT=development,
                                           # CORS_ORIGINS=["http://localhost:3003"]
uv sync && uv run alembic upgrade head
uv run pytest                              # 68 tests du moteur de règles
uv run uvicorn app.main:app --port 8004 --reload

cd frontend
echo 'NEXT_PUBLIC_API_URL=http://localhost:8004' > .env.local
pnpm install && pnpm dev                   # http://localhost:3003
```

Docker ne sert qu'ici : en production la base est le PostgreSQL du VPS.

---

## Entraîner les bots (`ml/`, hors production)

Nécessite un venv avec torch (voir `ml/train_v2.py`). Résumé :

```bash
python ml/train_v2.py --minutes 360 --workers 5 --envs 48 --out v2        # PPO en ligue, 2-5 joueurs
python ml/export_policy2.py v2.best.pt backend/app/bot_policy_v2.npz      # export numpy + critique
python ml/check_obs_parity2.py                                            # serveur == entraînement
python ml/ladder.py backend/app/bot_policy_v2.npz backend/app/bot_policy_v2_critic.npz   # Elo
```

La politique jouée par le serveur est celle de `backend/app/botbrain.py` ; `ml/search.py`
et `ml/ladder.py` l'évaluent hors ligne avec ce même code.
