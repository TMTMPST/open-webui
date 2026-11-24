# Use a personal Claude subscription in Open WebUI

This opt-in [Pipe Function](https://docs.openwebui.com/features/extensibility/plugin/functions/pipe/) runs the official, unmodified Claude Code CLI as the Open WebUI backend's OS user. It is for one person using their own Pro, Max, or Ultra account on a private instance, not a publicly hosted or shared service. It handles text chats with Sonnet; the reply appears after the CLI finishes. It does not expose Claude Code tools, attachments, or native tool calling.

Anthropic [does not permit third-party Claude.ai sign-in](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use), but explicitly distinguishes an end user signing into the unmodified CLI with their own subscription. Anthropic [documents `claude -p` for programmatic use](https://code.claude.com/docs/en/headless) and [says it draws from subscription limits with a Claude plan sign-in](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan). Claude Console sign-in is separate and can be billed as API usage **even without an API key**. The Pipe requires the CLI to report a paid personal Claude.ai login, does not inherit API credentials or provider overrides, and has no API fallback.

## Set up

1. On the **backend** machine, [install the latest official native Claude Code CLI](https://code.claude.com/docs/en/setup#install-claude-code) as the same non-root OS user that runs Open WebUI. The default executable is `$HOME/.local/bin/claude`; for a different install location, set `OPEN_WEBUI_CLAUDE_CODE_BINARY` to the executable's absolute path in the backend environment and restart. On macOS, run the backend in the same login session so the CLI can reach that user's Keychain. If the backend runs in a Linux container, install the CLI **inside** the container, sign in there as the backend UID (for example, from `docker exec -it --user <backend-uid> <container> sh`), and persist that user's `$HOME/.claude-open-webui` directory. A host login does not sign a container in.
2. Under that OS user, in a shell without Claude credential or provider overrides, run the following and choose your paid **Claude account**, not **Claude Console**. Use this dedicated CLI directory only for the subscription, not for Console keys, credential helpers, or gateways. Use an unmanaged installation without organization-managed credential or provider settings; the Pipe does not override admin policy. Do not copy Keychain entries, credential files, or tokens into Open WebUI.

   ```sh
   export CLAUDE_CONFIG_DIR="$HOME/.claude-open-webui"
   "$HOME/.local/bin/claude" auth login
   "$HOME/.local/bin/claude" auth status --text
   ```

   If you set a custom executable path, use that same executable for both commands. Check that status names your Claude plan, not Claude Console. In [Claude → Settings → Usage](https://claude.ai/settings/usage), turn off **Usage credits** (also called **Extra usage**) if you want requests to stop at the plan limit instead of incurring [pay-as-you-go overage](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans). Only Claude's account settings control this; the Pipe cannot change it.
3. As the Open WebUI admin, open **Admin Panel → Functions → Create**. Set the ID to `claude_subscription`, the name to **Claude Subscription (Personal)**, and the description to `Text chat using my local Claude Code subscription login`. Replace all the example code with the contents of [`scripts/claude_subscription_pipe.py`](../scripts/claude_subscription_pipe.py), click **Save & Create**, then turn on the function's switch. If Functions are disabled on the backend, enable `ENABLE_PLUGINS` and `ENABLE_FUNCTIONS` and restart. Do not add an Anthropic connection or key for this model.
4. Start a **New Chat**, select **Claude Subscription (Personal)**, and send `Reply with exactly: subscription smoke test`. Use a fresh text-only chat with tools and attachments off. The expected assistant message is `subscription smoke test`. With Usage credits off, the paid plan shown by the CLI and the successful response establish that the configured route used the plan. The CLI's estimated dollar cost is not a billing receipt.

## If the chat fails

- **Cannot start Claude Code:** check the executable path and permissions in the backend runtime, not on the browser machine.
- **Sign-in missing, expired, or unrecognized:** repeat `claude auth login` with the dedicated `CLAUDE_CONFIG_DIR` under the backend OS user. The Pipe refuses to send anything if the CLI cannot confirm the right account type and plan.
- **Usage limit reached:** check Claude's **Settings → Usage** for the reset and retry after it. No API key is tried.
