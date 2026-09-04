#!/usr/bin/env bash
# Mise à jour — à lancer sur le serveur depuis /var/www/9to1
set -euo pipefail
cd "$(dirname "$0")"

echo "==> git pull"
git pull

echo "==> Backend : dépendances + migrations"
cd backend
uv sync
uv run alembic upgrade head
cd ..

echo "==> Frontend : dépendances + build"
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..

echo "==> Redémarrage des services"
sudo systemctl restart 9to1-backend 9to1-frontend

echo "==> Déploiement terminé"
sudo systemctl status 9to1-backend 9to1-frontend --no-pager -l | head -20
