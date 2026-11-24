# Run personal subscription Open WebUI in Docker

Open Docker Desktop (or start your Docker engine). From the root of this fork's `claude-subscription` branch, run:

```sh
docker compose -f docker-compose.subscription.yaml up --build -d --wait
```

Open [http://localhost:3030](http://localhost:3030). This serves both the UI and backend from one container; no Vite, local Python environment, or Ollama server is needed. For a different port, set `OPEN_WEBUI_SUBSCRIPTION_PORT` when running Compose. The port is published only to loopback. Keep this instance private.

1. Create the first Open WebUI account (the administrator), then open **Admin Panel → Functions → Personal subscription sign-in**. Choose **Connect ChatGPT** or **Connect Claude** and follow the provider's browser sign-in. Use your subscription account, not an API key or Claude Console. Both official CLIs run as the non-root `webui` user in the container; no host CLI or login is needed.
2. The model is enabled automatically after sign-in. If the CLI is already signed in, the panel shows **Connected** without asking you to sign in again. Select **Chat with ChatGPT** or **Chat with Claude**, or pick the model in **New Chat**.
3. Send `Reply with exactly: subscription smoke test`. Expect `subscription smoke test`. No separately billed API key is needed. See the [ChatGPT](chatgpt-subscription.md) and [Claude](claude-subscription.md) guides for usage limits and overage settings.

The `webui-data` named volume keeps accounts, chats and Functions. The separate `cli-home` named volume keeps the CLIs' own sessions across rebuilds. Do not run `down -v` unless you intend to remove both volumes. Do not copy session files to the host or share the CLI volume.

To see why startup failed:

```sh
docker compose -f docker-compose.subscription.yaml logs --tail=100 open-webui
```

To stop the instance without removing either volume:

```sh
docker compose -f docker-compose.subscription.yaml stop
```
