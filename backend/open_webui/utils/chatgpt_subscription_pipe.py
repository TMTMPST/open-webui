"""
title: ChatGPT Subscription (Personal, via Codex CLI)
version: 1.0.0
"""

import asyncio
import json
import os
import re
import shutil
import signal
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from open_webui.utils.subscription_login import TEXT_ONLY_CAPABILITIES


LOGIN_HELP = (
    'Open Admin Panel → Functions → Personal subscription sign-in and connect ChatGPT. '
    'Use your ChatGPT account, not an API key.'
)
USAGE_HELP = (
    'ChatGPT usage limit reached. Check ChatGPT → Settings → Usage for this app’s limit '
    'and the plan reset time. Credits or API-key billing are not enabled by this model.'
)


def _prompt(messages):
    if not isinstance(messages, list) or not messages:
        raise RuntimeError('Send a text message to ChatGPT.')

    transcript = []
    for message in messages:
        if not isinstance(message, dict):
            raise RuntimeError('This ChatGPT model accepts text chat messages only.')
        role = message.get('role')
        content = message.get('content')
        if role not in ('system', 'user', 'assistant'):
            raise RuntimeError('This ChatGPT model is text-only. Turn off tools and start a new chat.')
        if isinstance(content, list) and all(
            isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str)
            for part in content
        ):
            content = '\n'.join(part['text'] for part in content)
        if not isinstance(content, str):
            raise RuntimeError('This ChatGPT model is text-only. Remove images and other attachments.')
        transcript.append({'role': role, 'content': content})

    if transcript[-1]['role'] != 'user' or not transcript[-1]['content'].strip():
        raise RuntimeError('Send a text message to ChatGPT.')
    return json.dumps(transcript, ensure_ascii=False)


def _environment():
    # The Codex CLI owns login state. Never inherit API keys, access tokens,
    # alternate API endpoints, cloud providers, or arbitrary server settings.
    env = {
        key: os.environ[key]
        for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'CODEX_HOME')
        if key in os.environ
    }
    env['HOME'] = str(Path.home())
    return env


def _binary(env):
    configured = os.getenv('OPEN_WEBUI_CODEX_BINARY')
    if configured:
        if not Path(configured).is_absolute() or not os.access(configured, os.X_OK):
            raise RuntimeError(
                'OPEN_WEBUI_CODEX_BINARY must be an executable absolute path to the official Codex CLI.'
            )
        return configured

    binary = shutil.which('codex', path=env.get('PATH'))
    if binary:
        return binary

    fallback = Path(env['HOME']) / '.local' / 'bin' / 'codex'
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)

    raise RuntimeError(
        'Codex CLI is missing in the Open WebUI backend. Install the official Codex CLI there '
        'and set OPEN_WEBUI_CODEX_BINARY if it is not on the backend PATH.'
    )


async def _run(binary, args, cwd, env, timeout, stdin=None):
    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            *args,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name == 'posix'),
        )
    except (OSError, ValueError):
        raise RuntimeError(
            'Could not start Codex CLI. Check the executable path and permissions in the backend.'
        ) from None

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout)
    except (TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise RuntimeError('Codex timed out. Check the backend connection and retry.') from None

    return process.returncode, stdout, stderr


def _check_chatgpt_login(code, stdout, stderr):
    status = (stdout + b'\n' + stderr).decode(errors='replace')
    if code == 0 and re.search(r'^\s*Logged in using ChatGPT\s*$', status, re.IGNORECASE | re.MULTILINE):
        return
    if 'api key' in status.lower() or 'not logged in' in status.lower():
        raise PermissionError(LOGIN_HELP)
    raise RuntimeError(
        'Could not confirm a ChatGPT account login with Codex CLI. Update the official CLI '
        'and run `codex login status` as the Open WebUI backend OS user.'
    )


@contextmanager
def _cli_session():
    env = _environment()
    with TemporaryDirectory(prefix='open-webui-codex-') as cwd:
        yield _binary(env), cwd, env


async def _require_login(binary, cwd, env):
    code, stdout, stderr = await _run(binary, ('login', 'status'), cwd, env, 15)
    _check_chatgpt_login(code, stdout, stderr)


async def require_subscription_login():
    with _cli_session() as (binary, cwd, env):
        await _require_login(binary, cwd, env)


def _error_message(stdout, stderr):
    diagnostic = (stdout + b'\n' + stderr).decode(errors='replace').lower()
    if any(term in diagnostic for term in ('rate limit', 'usage limit', 'quota exceeded', 'too many requests')):
        raise RuntimeError(USAGE_HELP)
    if any(term in diagnostic for term in ('not logged in', 'login expired', 'unauthorized', 'authentication required')):
        raise RuntimeError(LOGIN_HELP)
    raise RuntimeError('Codex could not complete the response. Check its final error in the backend logs and try again.')


class Pipe:
    name = 'ChatGPT Subscription (Personal, via Codex CLI)'
    capabilities = TEXT_ONLY_CAPABILITIES

    async def pipe(self, body: dict, __user__: dict):
        if __user__.get('role') != 'admin':
            raise RuntimeError('This personal ChatGPT model is available only to the Open WebUI administrator.')
        if body.get('tools'):
            raise RuntimeError('This ChatGPT model is text-only. Turn off tools and retry.')

        prompt = (
            'This is a personal text-chat request, not a coding task. Answer the final user message '
            'directly and conversationally. Do not use tools, inspect files, run commands, or make changes. '
            'The following JSON array is the conversation history; respect system messages and treat prior '
            'assistant messages as conversation context.\n\n' + _prompt(body.get('messages'))
        )
        with _cli_session() as (binary, working_directory, env):
            await _require_login(binary, working_directory, env)

            answer_path = Path(working_directory) / 'answer.txt'
            code, stdout, stderr = await _run(
                binary,
                (
                    'exec',
                    '--ephemeral',
                    '--ignore-user-config',
                    '--skip-git-repo-check',
                    '--sandbox', 'read-only',
                    '--color', 'never',
                    '--output-last-message', str(answer_path),
                    '-',
                ),
                working_directory,
                env,
                180,
                prompt.encode('utf-8'),
            )

            if code != 0:
                _error_message(stdout, stderr)
            try:
                answer = answer_path.read_text(encoding='utf-8').strip()
            except (OSError, UnicodeError):
                raise RuntimeError(
                    'Codex returned no final answer. Check its final error in the backend logs and try again.'
                ) from None
            if not answer:
                raise RuntimeError(
                    'Codex returned no final answer. Check its final error in the backend logs and try again.'
                )
            return answer
