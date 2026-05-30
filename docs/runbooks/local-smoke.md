# Local Smoke Runbook

This runbook verifies a local `xianyu-tools` build without touching production `.env`, `state/`, cookies, NAS data, or any real user database.

## Scope

The smoke is intentionally read-only from the application API perspective:

- It only checks HTTP endpoints such as `/health`, `/`, and `/docs`.
- It does not create tasks.
- It does not update notification settings.
- It does not write to a production database.
- It should run with disposable local data directories.

## Preconditions

```bash
cd /root/projects/xianyu-tools
git status --short --branch
```

Expected:

- You are on the branch you want to test.
- No unrelated local changes are present.
- Docker is available if you want to run the container smoke.

## Option A: Smoke an already-running app

Use this when a local app or container is already listening on a port:

```bash
cd /root/projects/xianyu-tools
python3 scripts/smoke_check.py --base-url http://127.0.0.1:8000
```

The script performs GET requests only. It verifies:

- `GET /health` returns HTTP 200 and, when JSON, a healthy-looking payload.
- `GET /` returns HTML for the Web UI shell.
- `GET /docs` returns HTTP 200 or 401/403 if protected by authentication middleware.

## Option B: Disposable Docker smoke

This path builds from the local source tree and uses temporary runtime directories.

```bash
cd /root/projects/xianyu-tools

docker build --pull=false -t xianyu-tools:smoke .

SMOKE_ROOT=$(mktemp -d /tmp/xianyu-tools-smoke.XXXXXX)
mkdir -p "$SMOKE_ROOT"/{data,state,prompts,logs,images,jsonl,price_history}
touch "$SMOKE_ROOT/config.json"
cat > "$SMOKE_ROOT/.env" <<'ENV'
WEB_USERNAME=admin
WEB_PASSWORD=admin123
OPENAI_API_KEY=smoke-only-placeholder
OPENAI_BASE_URL=http://127.0.0.1:9/v1
OPENAI_MODEL_NAME=smoke-model
RUN_HEADLESS=true
APP_DATABASE_FILE=/app/data/app.sqlite3
SERVER_PORT=8000
ENV

docker run -d --rm \
  --name xianyu-tools-smoke \
  -p 18000:8000 \
  -v "$SMOKE_ROOT/.env:/app/.env" \
  -v "$SMOKE_ROOT/data:/app/data" \
  -v "$SMOKE_ROOT/state:/app/state" \
  -v "$SMOKE_ROOT/prompts:/app/prompts" \
  -v "$SMOKE_ROOT/logs:/app/logs" \
  -v "$SMOKE_ROOT/images:/app/images" \
  -v "$SMOKE_ROOT/config.json:/app/config.json" \
  -v "$SMOKE_ROOT/jsonl:/app/jsonl" \
  -v "$SMOKE_ROOT/price_history:/app/price_history" \
  xianyu-tools:smoke

python3 scripts/smoke_check.py --base-url http://127.0.0.1:18000 --timeout 60

docker logs --tail 120 xianyu-tools-smoke

docker stop xianyu-tools-smoke
rm -rf "$SMOKE_ROOT"
```

## Option C: Docker Compose smoke with disposable env

Only use this if you intentionally want to exercise `docker-compose.yaml` itself. Do not point Compose at production `.env` / `state`.

Recommended pattern:

1. Create a temporary copy of the repository or override all bind mounts to temporary directories.
2. Use placeholder AI settings as shown in Option B.
3. Run only read-only endpoint checks with `scripts/smoke_check.py`.

## Expected success signal

The smoke is successful when:

- container or app starts without obvious traceback in logs
- `/health` is reachable
- `/` serves the Web UI shell
- `/docs` is reachable or intentionally auth-protected
- no task/settings write endpoint was called

## Cleanup

```bash
docker stop xianyu-tools-smoke 2>/dev/null || true
rm -rf /tmp/xianyu-tools-smoke.*
```

## Troubleshooting

- If the Docker build fails while fetching a base image, check Docker proxy / registry access first. This is not necessarily an application failure.
- If `/health` is not ready immediately, rerun `scripts/smoke_check.py --timeout 120` and inspect `docker logs xianyu-tools-smoke`.
- If the app starts but `/` is missing assets, run `cd web-ui && npm run build` locally and rebuild the image.
- If the smoke DB appears under `data/`, verify that it lives under the temporary `$SMOKE_ROOT`, not the repository production mount.
