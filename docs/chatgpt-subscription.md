# Use a ChatGPT plan in Open WebUI through Codex CLI

This opt-in [Pipe Function](https://docs.openwebui.com/features/extensibility/plugin/functions/pipe/) runs the **official Codex CLI** on the Open WebUI backend for the administrator's private, text-only chats. Codex's own ChatGPT sign-in manages account credentials. The Pipe does not implement ChatGPT OAuth, copy or read login tokens, use an OpenAI API key, or fall back to one. It returns a reply after Codex finishes; images and chat tools are not supported. Keep this to a private instance you control; don't expose Codex execution to untrusted users.

OpenAI documents **ChatGPT account sign-in** as subscription access for Codex CLI and describes `codex exec` as its non-interactive CLI for scripts. Its Codex SDK documentation recommends the SDK or app server for deeper product integrations; this Pipe intentionally uses the supported CLI rather than implementing a ChatGPT login flow. On the CLI's ChatGPT account route, Codex activity draws on the ChatGPT plan's Codex allowance and limits, not API usage billed to an API key. This is not a direct Open WebUI sign-in integration or a claim that Open WebUI is in OpenAI's third-party-app partner directory.

- [Codex authentication](https://developers.openai.com/codex/auth)
- [Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [Codex SDK and app server](https://learn.chatgpt.com/docs/codex-sdk)
- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [ChatGPT plan use in participating apps](https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites)

## Setup

1. Install the latest **official Codex CLI** on the Open WebUI **backend** machine, under the same OS account that runs the backend. From that account, run:

   ```sh
   codex login
   codex login status
   ```

   Complete **Sign in with ChatGPT** in the browser; do not choose API-key sign-in. Confirm the CLI prints `Logged in using ChatGPT`. The Pipe uses that account's normal Codex login directory (or `CODEX_HOME` when the backend environment sets it). On macOS, run the backend in the same login session so the CLI can reach that account's credential store. In a Linux container, install and sign in to Codex **inside the container** as the backend UID and persist that account's Codex home; a host login isn't visible inside the container. If the CLI is not on the backend's `PATH`, set `OPEN_WEBUI_CODEX_BINARY` to its absolute executable path in the backend environment and restart.
2. As the Open WebUI administrator, go to **Admin Panel → Functions → Create**. Set the ID to `chatgpt_subscription`, the name to **ChatGPT Subscription (Personal, via Codex CLI)**, and the description to `Private text chat using my local ChatGPT sign-in through Codex CLI`. Replace the example code with [`scripts/chatgpt_subscription_pipe.py`](../scripts/chatgpt_subscription_pipe.py), click **Save & Create**, and enable the Function. If Functions are disabled, set `ENABLE_PLUGINS` and `ENABLE_FUNCTIONS` on the backend and restart. Do not create or attach an OpenAI API connection for this model.
3. Start a **New Chat**, select **ChatGPT Subscription (Personal, via Codex CLI)**, and send `Reply with exactly: ChatGPT subscription smoke test`.

Codex uses the signed-in account's current default model. Its runs consume the Codex allowance and are subject to the account's plan, workspace and service limits. To avoid unexpected charges after included usage, check **ChatGPT → Settings → Usage** and disable app use of credits or automatic credit purchases if those options are available and you don't want them. This Pipe never switches to an API key. ChatGPT usage and credits are governed by the account's own controls; the Pipe cannot change them.

## If the chat fails

- **Codex CLI missing:** install it on the backend under the backend OS account; set `OPEN_WEBUI_CODEX_BINARY` if it is outside that process's `PATH`.
- **Not signed in, expired, or API-key login:** as the backend user, run `codex login`, choose **Sign in with ChatGPT**, and check `codex login status` reports `Logged in using ChatGPT`. The Pipe refuses API-key login and does not make a request until this check passes.
- **Usage limit:** check **ChatGPT → Settings → Usage** for the account or workspace limit and reset time. Retry when available. There is no API fallback.
- **Other CLI failure:** update Codex CLI, verify the account can run `codex exec` from the backend, and inspect its local error there. The Pipe does not expose raw CLI logs or login information in chat.
