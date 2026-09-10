#!/usr/bin/env bash
set -e

# Usa python3 si existe, si no python (en Render python está disponible)
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

echo "==> Aplicando migraciones..."
$PY manage.py migrate --noinput

echo "==> Inicializando usuarios predeterminados..."
$PY manage.py init_users

echo "==> Recopilando archivos estáticos..."
$PY manage.py collectstatic --noinput

echo "==> Creando carpeta media..."
mkdir -p media

echo "==> Iniciando servidor..."
gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --access-logfile - --error-logfile -