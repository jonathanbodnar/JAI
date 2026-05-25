# Kokoro TTS sidecar

We don't ship custom code here. Kokoro-FastAPI is a prebuilt OpenAI-compatible
TTS server that wraps the Kokoro-82M model. We just deploy its image.

## Local

```bash
docker compose -f ../../infra/docker-compose.dev.yml up kokoro
# → http://localhost:8880
```

## Fly.io

```bash
fly launch --image ghcr.io/remsky/kokoro-fastapi-cpu:latest --copy-config --no-deploy
fly deploy
```

The backend (`apps/api`) talks to this via `KOKORO_TTS_URL`.

## Swap to GPU later

Change the image to `ghcr.io/remsky/kokoro-fastapi-gpu:latest` and pick a Fly
GPU machine (`a10` or `l40s`). 5–10× faster, still cheap.
