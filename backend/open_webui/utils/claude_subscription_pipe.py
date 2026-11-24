"""
title: Claude Subscription (Personal)
version: 1.0.0
"""

import asyncio
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from open_webui.utils.subscription_login import TEXT_ONLY_CAPABILITIES, selected_model


LOGIN_HELP = (
    'Open Admin Panel → Functions → Personal subscription sign-in and connect Claude. '
    'Choose your paid Claude plan, not Claude Console.'
)
USAGE_HELP = 'Claude usage limit reached. Check Settings > Usage at claude.ai and retry after the limit resets.'


def _prompt(messages):
    if not isinstance(messages, list) or not messages:
        raise RuntimeError('Send a text message to Claude.')
    transcript = []
    for message in messages:
        if not isinstance(message, dict):
            raise RuntimeError('This Claude model expects text chat messages.')
        role = message.get('role')
        content = message.get('content')
        if role not in ('system', 'user', 'assistant'):
            raise RuntimeError('This Claude model is text-only. Turn off tools and start a new chat.')
        if isinstance(content, list) and all(
            isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str)
            for part in content
        ):
            content = '\n'.join(part['text'] for part in content)
        if not isinstance(content, str):
            raise RuntimeError('This Claude model is text-only. Remove images and other attachments.')
        transcript.append({'role': role, 'content': content})
    if transcript[-1]['role'] != 'user' or not transcript[-1]['content'].strip():
        raise RuntimeError('Send a text message to Claude.')
    return json.dumps(transcript, ensure_ascii=False).encode('utf-8')


async def _run(binary, args, cwd, env, timeout, prompt=b''):
    try:
        process = await asyncio.create_subprocess_exec(
            binary, *args, cwd=cwd, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError):
        raise RuntimeError(
            'Cannot start Claude Code. Install the official native CLI on the Open WebUI backend '
            'and check that OPEN_WEBUI_CLAUDE_CODE_BINARY points to its executable.'
        ) from None

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(prompt), timeout)
    except (TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise RuntimeError('Claude Code timed out. Check the backend network and retry.') from None

    try:
        result = json.loads(stdout)
    except (ValueError, UnicodeError):
        result = None
    return process.returncode, result if isinstance(result, dict) else {}, stdout, stderr


def _reply(code, result, stdout, stderr):
    text = result.get('result')
    if (
        code == 0 and result.get('type') == 'result' and result.get('subtype') == 'success'
        and result.get('is_error') is False and isinstance(text, str) and text.strip()
    ):
        return text

    # CLI errors may appear in JSON, plain stdout, or stderr. Never relay raw diagnostics.
    diagnostic = (stdout + stderr).decode(errors='replace').lower()
    status = result.get('api_error_status')
    if status == 429 or any(marker in diagnostic for marker in (
        'rate limit', 'hit your limit', 'you\'ve hit your ', 'usage limit', 'usage credits',
    )):
        raise RuntimeError(USAGE_HELP)
    if status == 401 or any(marker in diagnostic for marker in (
        'not logged in', 'not signed in', '/login', 'login expired', 'oauth', 'failed to authenticate',
    )):
        raise RuntimeError(LOGIN_HELP)
    raise RuntimeError('Claude Code could not reply. Check that the official CLI is up to date and can reach Anthropic from the backend.')


@contextmanager
def _cli_session():
    import pwd

    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir)
    binary = Path(os.getenv('OPEN_WEBUI_CLAUDE_CODE_BINARY', str(home / '.local/bin/claude')))
    if not binary.is_absolute():
        raise RuntimeError('Set OPEN_WEBUI_CLAUDE_CODE_BINARY to the absolute path of the official Claude executable.')

    # Do not inherit API keys, OAuth tokens, gateways, cloud routing, or CLI settings overrides.
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ}
    env.update(
        HOME=str(home), USER=account.pw_name, LOGNAME=account.pw_name,
        CLAUDE_CONFIG_DIR=str(home / '.claude-open-webui'),
    )
    with TemporaryDirectory(prefix='open-webui-claude-') as cwd:
        # The CLI can otherwise switch to a saved Console profile when a login expires.
        env['ANTHROPIC_CONFIG_DIR'] = cwd
        yield binary, cwd, env


async def _require_login(binary, cwd, env):
    code, status, _, _ = await _run(binary, ('auth', 'status', '--json'), cwd, env, 15)
    if not status:
        raise RuntimeError('Could not check Claude Code sign-in. Update the native CLI and run `claude auth status` on the backend.')
    if code or status.get('loggedIn') is not True:
        raise PermissionError(LOGIN_HELP)
    if (
        status.get('authMethod') != 'claude.ai'
        or status.get('apiProvider') != 'firstParty'
        or status.get('subscriptionType') not in ('pro', 'max', 'ultra')
        or status.get('apiKeySource') is not None
    ):
        raise PermissionError('Claude Code did not report a first-party paid personal subscription. ' + LOGIN_HELP)
    return status['subscriptionType']


_models = ()
_STANDARD_MODELS = (
    {'id': 'claude-sonnet-5-5', 'name': 'Claude Sonnet 5.5', 'description': 'Balanced model for everyday work.'},
    {'id': 'claude-opus-5-5', 'name': 'Claude Opus 5.5', 'description': 'Complex reasoning and demanding work.'},
    {'id': 'claude-haiku-5-5', 'name': 'Claude Haiku 5.5', 'description': 'Fast model for simpler tasks.'},
)
_FABLE_MODELS = tuple(
    {
        'id': 'claude-fable-' + version.replace('.', '-'),
        'name': 'Claude Fable ' + version,
        'description': 'Included on Max and Ultra up to the Fable limit. Usage credits may apply after that.',
    }
    for version in ('5.2', '5.1', '5')
)


def models_for_plan(plan):
    return _STANDARD_MODELS + _FABLE_MODELS if plan in ('max', 'ultra') else _STANDARD_MODELS


def subscription_models():
    return _models


async def refresh_subscription_models():
    global _models
    with _cli_session() as (binary, cwd, env):
        plan = await _require_login(binary, cwd, env)
    _models = models_for_plan(plan)
    return _models


class Pipe:
    pipes = staticmethod(subscription_models)
    capabilities = TEXT_ONLY_CAPABILITIES

    async def pipe(self, body: dict, __user__: dict):
        if __user__.get('role') != 'admin':
            raise RuntimeError('This personal Claude model is available only to the Open WebUI administrator.')
        if body.get('tools'):
            raise RuntimeError('This Claude model is text-only. Turn off tools and retry.')
        prompt = _prompt(body.get('messages'))

        with _cli_session() as (binary, cwd, env):
            plan = await _require_login(binary, cwd, env)
            model = selected_model(body, 'claude', models_for_plan(plan))
            return _reply(*await _run(
                binary,
                (
                    '--print', '--output-format', 'json', '--model', model,
                    '--safe-mode', '--setting-sources', '', '--strict-mcp-config', '--tools', '',
                    '--permission-mode', 'dontAsk', '--disable-slash-commands', '--no-session-persistence',
                    '--system-prompt', 'You are a text chat assistant. The input is a JSON array of '
                    'conversation turns with role and content fields. Honor system turns as instructions '
                    'and answer the final user turn in the context of the earlier turns.',
                ),
                cwd, env, 180, prompt,
            ))
