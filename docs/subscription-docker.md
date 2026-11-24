# Run personal subscription Open WebUI in Docker

Open Docker Desktop (or start your Docker engine). From the root of this fork's `claude-subscription` branch, run:

```sh
docker compose -f docker-compose.subscription.yaml up --build -d --wait
```

Open [http://localhost:3030](http://localhost:3030). This serves both the UI and backend from one container; no Vite, local Python environment, or Ollama server is needed. For a different port, set `OPEN_WEBUI_SUBSCRIPTION_PORT` when running Compose. The port is published only to loopback. Keep this instance private.

1. Create the first Open WebUI account (the administrator), then open **Admin Panel → Functions → Personal subscription sign-in**. Choose **Connect ChatGPT** or **Connect Claude** and follow the provider's browser sign-in. Use your subscription account, not an API key or Claude Console. Both official CLIs are already in the container and run as the non-root `webui` user. You do not need to install or sign into either CLI on the host.
2. Add and enable the Function once: [ChatGPT setup step 2](chatgpt-subscription.md#setup) or [Claude setup step 3](claude-subscription.md#set-up). The Function scripts are in this checkout's `scripts/` directory.
3. Start a **New Chat**, choose the installed subscription model, and send `Reply with exactly: subscription smoke test`. Expect `subscription smoke test`. No separately billed API key is needed for either Function. See the provider guides for usage limits and overage settings.

The `webui-data` named volume keeps accounts, chats and Functions. The separate `cli-home` named volume keeps the CLIs' own sessions across rebuilds. Do not run `down -v` unless you intend to remove both volumes. Do not copy session files to the host or share the CLI volume.

To see why startup failed:

```sh
docker compose -f docker-compose.subscription.yaml logs --tail=100 open-webui
```

To stop the instance without removing either volume:

```sh
docker compose -f docker-compose.subscription.yaml stop
```
