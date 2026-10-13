# hub-next

## Desarrollo local

```bash
git submodule update --init          # packages/live y packages/ui (ERPlora/live, ERPlora/ui)
printf 'DEBUG=True\n' > .env         # sin DEBUG, el hub arranca como producción
uv sync && pnpm install
uv run python manage.py runserver    # Django en a.localhost:8000 y Vite (`pnpm run dev`)
uv run pytest -q                     # Postgres de compose.yaml (`docker compose up -d`)
```

`DEBUG` está apagado si no se define: sin `DEBUG=True` en `.env` (o en el entorno), los ajustes
exigen `SECRET_KEY`, `SAAS_URL` e `INTERNAL_SHARED_SECRET`, como en producción. Con `DEBUG=True`
el resto de variables toma los valores locales por defecto (lista completa en el `.env.example` de
erplora-next). `.env` nunca se sube al repo.
