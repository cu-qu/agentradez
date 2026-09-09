# Agentradez web

User-facing Next.js app for the Agentradez API. Connect a broker, pick Copy Trade + a risk tier, then watch automation.

The API must already be running at [http://localhost:8001](http://localhost:8001). The browser calls that origin directly, including when this app runs in Docker.

## Cursor: reopen in the Dev Container, then F5

The reopen toast only appears when this folder is opened or the window is reloaded. If you are already in the folder, run:

1. `Cmd+Shift+P` → **Dev Containers: Reset Don't Show Reopen Notification** (if you ever clicked Don't Show Again)
2. `Cmd+Shift+P` → **Developer: Reload Window**
3. Click **Reopen in Container** on the toast, or run **Dev Containers: Reopen in Container**

When the container is ready, **Run and Debug** → **Next.js: dev**. Next.js listens on port 3000 (Cursor forwards it).

## Docker Compose (without the Dev Container)

```bash
./scripts/start_frontend.sh
```

Stop with `./scripts/stop_frontend.sh`.

## Host (no Docker)

```bash
cp .env.example .env.local
npm install
npm run dev
```

App: [http://localhost:3000](http://localhost:3000)

Refresh generated types after backend schema changes:

```bash
npm run generate:api
```

Inside the Dev Container that script also tries `host.docker.internal:8001` so it can reach the API on your machine.

| | |
|---|---|
| Web | `http://localhost:3000` |
| API | `http://localhost:8001` |
| Schema | `http://localhost:8001/api/schema/` |
| Env | `NEXT_PUBLIC_API_URL=http://localhost:8001` |

Auth stores the access token in memory and the refresh token in `localStorage`. Email verification is optional for trading; `/verify-email` exists so backend email links work.
