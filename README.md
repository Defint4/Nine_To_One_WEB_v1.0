# Games

Plateforme de jeux multijoueurs en temps réel, pensée pour le téléphone : on entre un
pseudo, on choisit un jeu, on crée une table, on partage son code, et on joue. Une seule
application (PWA), une seule identité, un module par jeu.

- Frontend : Next.js 16 (PWA mobile), servi par `next start` sur le port 3003.
- Backend : FastAPI + WebSocket, PostgreSQL pour les profils et les stats, tables en
  mémoire (un seul processus). Port 8003.
- Production : https://games.matthieuguiot.dev

| Jeu | Slug | Joueurs | Doc |
|---|---|---|---|
| Nine to One | `nine-to-one` | 2 à 5, bots à 3 niveaux | [docs/nine-to-one](docs/nine-to-one/README.md) |
| Goulag | `goulag` | 2 à 6, bots à 2 niveaux (interface à venir) | [docs/goulag](docs/goulag/README.md) |

```
backend/
  app/core/        config, base de données, JWT, rate limiting
  app/players/     identité par pseudo + avatar, stats par jeu
  app/rooms/       tables : sièges, WebSocket, chat, emotes, timer de tour, revanche, bots
  app/games/       base.py (contrat GameSpec), registry.py, puis un dossier par jeu
frontend/
  src/app/         / (identité) puis une route par jeu : /<slug>, /<slug>/table/[code]
  src/components/  partagés : avatars, cartes, feuilles, chat, vols de cartes, verrou mobile
  src/games/       un dossier par jeu (écrans, socket, types)
  src/lib/         api, identité, catalogue des jeux (games.ts), sons, préférences
deploy/            services systemd + configuration nginx
docs/              un dossier par jeu : règles, architecture du module, bots
ml/                entraînement des bots, un dossier par jeu (torch, hors production)
```

---

## Ajouter un jeu

Tout ce qui est commun existe déjà : identité, tables, sièges, WebSocket, reconnexion,
chat, emotes, timer de tour, revanche, stats, PWA. Un jeu n'écrit que ses règles, sa vue
et ses écrans.

**Backend** — `backend/app/games/<slug>/` :

1. `engine/` : les règles, pures (aucune I/O), avec leurs tests dans `tests/`. L'état
   utilise `GameStatus` de `app.games.base` (lobby / playing / finished) et lève
   `GameError` (ou une sous-classe) sur coup illégal.
2. `views.py` : ce que chaque siège a le droit de voir (jamais les cartes des autres).
3. `spec.py` : une sous-classe de `GameSpec` (`app/games/base.py`) — création d'état,
   `handle_action` (messages WebSocket → moteur), `view`, `auto_play` (timer écoulé),
   `results` (gagnant, perdant), et les bots si le jeu en a.
4. Une ligne dans `app/games/registry.py`.

**Frontend** — `frontend/src/games/<slug>/` et `frontend/src/app/<slug>/` :

1. `types.ts` : `RoomView` / `PlayerView` du jeu, qui étendent `BaseRoomView` /
   `BasePlayerView` de `src/lib/types.ts` (mêmes champs que `views.py`).
2. `socket.ts` : `useRoomSocket<RoomView>` + les actions du jeu via `send`.
3. Les écrans (accueil du jeu, lobby, table), puis deux routes minces dans
   `src/app/<slug>/page.tsx` et `src/app/<slug>/table/[code]/page.tsx`.
4. Une entrée dans `src/lib/games.ts` (le catalogue affiché à la sélection).

**Doc** — `docs/<slug>/README.md` : règles, arbitrages, architecture du module.

**Serveur** — rien de spécifique : `./deploy.sh` (voir « Mises à jour »). Les stats par
jeu sont stockées par slug, aucune migration n'est nécessaire pour un nouveau jeu.

---

## Déploiement en production — `games.matthieuguiot.dev`

Même VPS que `portfolio-2026`, `concreteFencing` et `invoice_Maker` (Ubuntu 24.04,
utilisateur `matthieu`, nginx + certbot + PostgreSQL + uv + Node 22 + pnpm déjà installés).

| | |
|---|---|
| Dossier | `/var/www/games` |
| Services | `games-backend` (port 8003) · `games-frontend` (port 3003) |
| Ports déjà pris | 8000/3000 portfolio · 8001/3001 concrete · 8002/3002 invoice |
| Base | rôle et base PostgreSQL `games` |

### 0. DNS

Chez Cloudflare (zone `matthieuguiot.dev`), un enregistrement **A** :

```
games.matthieuguiot.dev  →  IP du VPS
```

En « DNS only » (nuage gris) le temps de générer le certificat.

### 1. PostgreSQL — rôle et base dédiés

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE games WITH LOGIN PASSWORD 'MOT_DE_PASSE_FORT';
CREATE DATABASE games OWNER games;
\q
```

### 2. Récupérer le code

Une deploy key GitHub est scopée à un seul repo : en créer une dédiée.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_games -C "vps-games-deploy" -N ""
cat ~/.ssh/github_games.pub
```

Coller la clé publique dans GitHub → repo `Defint4/Games` → *Settings → Deploy keys*
(lecture seule). Puis :

```bash
cat >> ~/.ssh/config << 'EOF'

Host github-games
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_games
    IdentitiesOnly yes
EOF

sudo mkdir -p /var/www/games
sudo chown matthieu:www-data /var/www/games
git clone github-games:Defint4/Games.git /var/www/games
chmod +x /var/www/games/deploy.sh
```

### 3. Backend

```bash
cd /var/www/games/backend
cp .env.example .env
nano .env
```

À renseigner :

```
DATABASE_URL=postgresql+asyncpg://games:MOT_DE_PASSE_FORT@localhost:5432/games
ENVIRONMENT=production
CORS_ORIGINS=["https://games.matthieuguiot.dev"]
JWT_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
BOT_TIME_BUDGET=0.5
BOT_THREADS=1
```

`JWT_SECRET` est obligatoire : l'API refuse de démarrer s'il fait moins de 32 caractères.
`BOT_TIME_BUDGET` / `BOT_THREADS` bornent le CPU consommé par le bot Difficile de Nine to
One (voir [docs/nine-to-one](docs/nine-to-one/README.md)).

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

Un seul worker uvicorn, toujours : les tables vivent dans la mémoire du processus.
Ne jamais ajouter `--workers`.

### 4. Frontend

L'adresse de l'API est embarquée dans le build (`NEXT_PUBLIC_API_URL`) : REST et
WebSocket passent par nginx sur le même domaine.

```bash
cd /var/www/games/frontend
cp .env.example .env.production
pnpm install --frozen-lockfile
pnpm build
```

### 5. Services systemd

```bash
sudo cp /var/www/games/deploy/games-backend.service /etc/systemd/system/
sudo cp /var/www/games/deploy/games-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now games-backend games-frontend
sudo systemctl status games-backend games-frontend
```

### 6. Nginx + HTTPS

```bash
sudo cp /var/www/games/deploy/nginx-games.conf /etc/nginx/sites-available/games
sudo ln -s /etc/nginx/sites-available/games /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d games.matthieuguiot.dev
```

La config nginx garde le WebSocket de partie ouvert (`proxy_read_timeout 3600s` sur
`/api/`) : sans cela, nginx couperait la connexion après 60 s de silence en lobby.

### 7. Vérifications

```bash
curl https://games.matthieuguiot.dev/api/health
sudo systemctl is-enabled games-backend games-frontend
sudo journalctl -u games-backend -n 30 --no-pager
```

Dans le navigateur, sur téléphone : entrer un pseudo, ouvrir Nine to One, créer une
table, ajouter un bot Difficile depuis le lobby (bouton « + » à droite des places libres),
se déclarer prêt et jouer une manche. Une fois le certificat en place, repasser l'entrée
DNS en proxy Cloudflare (nuage orange) si souhaité : le WebSocket passe sans réglage
particulier.

### 8. Mises à jour

```bash
cd /var/www/games
./deploy.sh
```

`git pull` → `uv sync` + migrations → `pnpm install` + build → restart des deux services.
Ajouter un jeu en production, c'est exactement cette commande.

### Commandes utiles

```bash
sudo journalctl -u games-backend -f
sudo journalctl -u games-frontend -f
sudo systemctl restart games-backend games-frontend
sudo -u postgres pg_dump games | gzip > ~/games-$(date +%F).sql.gz   # sauvegarde
```

### Retirer l'ancienne installation `9to1`

L'ancien déploiement (`/var/www/9to1`, `9to1.matthieuguiot.dev`) n'a jamais eu de joueur :
on le supprime au lieu de le migrer, avant l'étape 1.

```bash
sudo systemctl disable --now 9to1-backend 9to1-frontend
sudo rm /etc/systemd/system/9to1-backend.service /etc/systemd/system/9to1-frontend.service
sudo systemctl daemon-reload
sudo rm /etc/nginx/sites-enabled/9to1 /etc/nginx/sites-available/9to1
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name 9to1.matthieuguiot.dev
sudo rm -rf /var/www/9to1
sudo -u postgres psql -c "DROP DATABASE ninetoone;" -c "DROP ROLE ninetoone;"
```

Puis supprimer l'enregistrement DNS `9to1` chez Cloudflare et la deploy key
`vps-9to1-deploy` sur GitHub (le repo a été renommé, l'ancienne clé fonctionne encore : la
remplacer par `vps-games-deploy` à l'étape 2 et retirer l'ancienne).

---

## Développement local

```bash
docker compose up -d                       # PostgreSQL sur 127.0.0.1:5435

cd backend
cp .env.example .env                       # DATABASE_URL → games:games@127.0.0.1:5435/games,
                                           # ENVIRONMENT=development, CORS_ORIGINS=["http://localhost:3003"]
uv sync && uv run alembic upgrade head
uv run pytest                              # tests des moteurs de règles
uv run ruff check app && uv run ruff format --check app
uv run uvicorn app.main:app --port 8004 --reload

cd frontend
echo 'NEXT_PUBLIC_API_URL=http://localhost:8004' > .env.local
pnpm install && pnpm dev                   # http://localhost:3003
pnpm lint
```

Docker ne sert qu'ici : en production la base est le PostgreSQL du VPS.

---

## Comment ça tient ensemble

- **Identité** : pas de compte. `POST /api/players/enter` avec un pseudo et un avatar
  renvoie un jeton JWT longue durée, gardé sur l'appareil. Le pseudo est la clé (insensible
  à la casse). Les stats sont stockées par jeu (`player_game_stats`).
- **Tables** : `POST /api/rooms` avec le slug du jeu, `POST /api/rooms/{code}/join`,
  `GET /api/rooms?game=<slug>`. Puis `WS /api/rooms/{code}/ws?token=…`. Les codes (4
  chiffres) sont uniques tous jeux confondus ; la vue porte le champ `game`.
- **Le serveur est seul juge** : le client envoie des intentions (`{"action": …}`), reçoit
  une vue filtrée à chaque changement (`{"type": "state", "view", "events"}`). Les actions
  communes sont traitées par `app/rooms/router.py`, le reste va à `GameSpec.handle_action`.
- **Mobile** : sur téléphone, le site exige l'installation en PWA (`MobileGate.tsx`) ;
  sur ordinateur le navigateur suffit.
