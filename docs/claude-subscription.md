# Use a personal Claude subscription in Open WebUI

This opt-in [Pipe Function](https://docs.openwebui.com/features/extensibility/plugin/functions/pipe/) runs the official, unmodified Claude Code CLI as the Open WebUI backend's OS user. It is for one person using their own Pro, Max, or Ultra account on a private instance, not a publicly hosted or shared service. It handles text chats; replies appear after the CLI finishes. It does not expose Claude Code tools, attachments, or native tool calling.

Anthropic [does not permit third-party Claude.ai sign-in](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use), but explicitly distinguishes an end user signing into the unmodified CLI with their own subscription. Anthropic [documents `claude -p` for programmatic use](https://code.claude.com/docs/en/headless) and [says it draws from subscription limits with a Claude plan sign-in](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan). Claude Console sign-in is separate and can be billed as API usage **even without an API key**. The Pipe requires the CLI to report a paid personal Claude.ai login, does not inherit API credentials or provider overrides, and has no API fallback.

To run Open WebUI and Claude Code together without installing either on the host, use the [personal subscription Docker setup](subscription-docker.md).

## Browser sign-in (no terminal login)

Set `ENABLE_PERSONAL_SUBSCRIPTION_LOGIN=true` on the backend and restart. Use a private instance with WebUI authentication, Functions (`ENABLE_PLUGINS=true` and `ENABLE_FUNCTIONS=true`), one admin, and one backend worker. Install Claude Code on that backend first. In **Admin Panel → Functions → Personal subscription sign-in**, select **Connect Claude** and open the official link. If Claude shows a one-time login code, enter it in the panel and select **Verify code**. Open WebUI forwards that code directly to `claude auth login --claudeai`; only Claude Code stores its session. Never paste a session token or API key. Use HTTPS if accessing the panel from a different machine. When the CLI confirms the paid plan, Open WebUI automatically adds the model. Select **Chat with Claude** to start a chat.

## Set up

1. On the **backend** machine, [install the latest official native Claude Code CLI](https://code.claude.com/docs/en/setup#install-claude-code) as the same non-root OS user that runs Open WebUI. The default executable is `$HOME/.local/bin/claude`; for a different install location, set `OPEN_WEBUI_CLAUDE_CODE_BINARY` to the executable's absolute path in the backend environment and restart. On macOS, run the backend in the same login session so the CLI can reach that user's Keychain. If the backend runs in a Linux container, install the CLI **inside** the container, sign in there as the backend UID (for example, from `docker exec -it --user <backend-uid> <container> sh`), and persist that user's `$HOME/.claude-open-webui` directory. A host login does not sign a container in.
2. If you did not sign in through the panel, run the following under the backend OS user, in a shell without Claude credential or provider overrides. Choose your paid **Claude account**, not **Claude Console**. Use this dedicated CLI directory only for the subscription, not for Console keys, credential helpers, or gateways. Use an unmanaged installation without organization-managed credential or provider settings; the Pipe does not override admin policy. Do not copy Keychain entries, credential files, or tokens into Open WebUI.

   ```sh
   export CLAUDE_CONFIG_DIR="$HOME/.claude-open-webui"
   "$HOME/.local/bin/claude" auth login
   "$HOME/.local/bin/claude" auth status --text
   ```

   If you set a custom executable path, use that same executable for both commands. Check that status names your Claude plan, not Claude Console. In [Claude → Settings → Usage](https://claude.ai/settings/usage), turn off **Usage credits** (also called **Extra usage**) if you want requests to stop at the plan limit instead of incurring [pay-as-you-go overage](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans). Only Claude's account settings control this; the Pipe cannot change it.
3. Open **Admin Panel → Functions → Personal subscription sign-in** after enabling it as described above. Open WebUI adds the model for a qualifying saved sign-in without a second login. Do not add an Anthropic connection or key for this model.
4. Start a **New Chat**, select **Claude Sonnet 5.5**, and send `Reply with exactly: subscription smoke test`. Use a fresh text-only chat with tools and attachments off. The expected assistant message is `subscription smoke test`. With Usage credits off, the paid plan shown by the CLI and the successful response establish that the configured route used the plan. The CLI's estimated dollar cost is not a billing receipt.

The picker offers **Sonnet 5.5**, **Opus 5.5**, and **Haiku 5.5**, using exact Claude Code model IDs. Use Claude Code 2.1.321 or newer. It also offers **Fable 5.2**, **5.1**, and **5** on Max and Ultra. [Anthropic says](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan) Fable on Pro requires usage credits from the start, so it is not listed on Pro. On Max and Ultra, turn off Usage credits if you want Fable to stop rather than incur overage when the included allowance is reached. Claude Code's own safety fallback still applies.

## If the chat fails

- **Cannot start Claude Code:** check the executable path and permissions in the backend runtime, not on the browser machine.
- **Sign-in missing, expired, or unrecognized:** reconnect through the Functions panel, or repeat `claude auth login` with the dedicated `CLAUDE_CONFIG_DIR` as the backend OS user. The Pipe refuses to send anything if the CLI cannot confirm the right account type and plan.
- **Usage limit reached:** check Claude's **Settings → Usage** for the reset and retry after it. No API key is tried.
