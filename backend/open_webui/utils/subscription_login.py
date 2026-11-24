"""Short-lived login attempts for the private subscription Pipes."""

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4


@dataclass
class LoginAttempt:
    owner: str
    provider: str
    id: str = field(default_factory=lambda: uuid4().hex)
    state: str = 'starting'
    url: str | None = None
    device_code: str | None = None
    detail: str | None = None
    code: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1), repr=False)
    task: asyncio.Task | None = field(default=None, repr=False)

    def public(self):
        return {
            'id': self.id, 'state': self.state, 'url': self.url,
            'device_code': self.device_code, 'detail': self.detail,
        }

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def run(self):
        try:
            async with asyncio.timeout(600):
                with TemporaryDirectory(prefix='open-webui-subscription-login-') as cwd:
                    binary, args, env = cli(self.provider, cwd)
                    process = await asyncio.create_subprocess_exec(
                        binary, *args, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL if self.provider == 'chatgpt' else asyncio.subprocess.STDOUT,
                    )
                    try:
                        async with asyncio.timeout(30):
                            if self.provider == 'chatgpt':
                                login_id = await self.start_codex(process)
                            else:
                                await self.start_claude(process)
                        if self.provider == 'chatgpt':
                            await self.finish_codex(process, login_id)
                        else:
                            await self.finish_claude(process)
                    finally:
                        if process.returncode is None:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                            await process.communicate()
            self.state = 'connected'
        except TimeoutError:
            self.state, self.detail = 'failed', 'Sign-in timed out. Start a new attempt.'
        except asyncio.CancelledError:
            self.state = 'cancelled'
            raise
        except (OSError, ValueError, RuntimeError):
            self.state = 'failed'
            self.detail = (
                'Could not complete sign-in. Check that the official CLI is installed and up to date. '
                + ('Enable device-code authorization in ChatGPT security settings, then retry.'
                   if self.provider == 'chatgpt' else 'Use the code from the official Claude page and retry.')
            )
        finally:
            self.url = self.device_code = None
            if not self.code.empty():
                self.code.get_nowait()

    async def start_codex(self, process):
        await send(process, {
            'id': 1, 'method': 'initialize',
            'params': {'clientInfo': {'name': 'open-webui', 'title': 'Open WebUI', 'version': '1.0.0'}},
        })
        await result(process, 1)
        await send(process, {'method': 'initialized', 'params': {}})
        await send(process, {'id': 2, 'method': 'account/login/start', 'params': {'type': 'chatgptDeviceCode'}})
        reply = await result(process, 2)
        url = official_url(reply.get('verificationUrl'), {'auth.openai.com'})
        code, login_id = reply.get('userCode'), reply.get('loginId')
        if not isinstance(login_id, str) or not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9-]{4,32}', code):
            raise ValueError('Invalid device challenge')
        self.url, self.device_code, self.state = url, code, 'waiting'
        return login_id

    async def finish_codex(self, process, login_id):
        while True:
            message = await receive(process)
            if message.get('method') != 'account/login/completed':
                continue
            params = message.get('params', {})
            if params.get('loginId') == login_id:
                if params.get('success') is not True:
                    raise ValueError('Device sign-in failed')
                return

    async def start_claude(self, process):
        output = bytearray()
        while len(output) < 32768:
            chunk = await process.stdout.read(4096)
            if not chunk:
                break
            output.extend(chunk)
            match = re.search(rb"visit:\s*(https://[^\s]+)", output)
            if match and b'Paste code here if prompted' in output:
                self.url = official_url(match[1].decode('ascii'), {'claude.com', 'claude.ai'})
                self.state = 'waiting'
                return
        raise ValueError('Missing Claude sign-in prompt')

    async def finish_claude(self, process):
        # The browser may complete the CLI's loopback callback without a manual code.
        output = asyncio.create_task(process.stdout.read())
        wait_code = asyncio.create_task(self.code.get())
        try:
            done, _ = await asyncio.wait((output, wait_code), return_when=asyncio.FIRST_COMPLETED)
            if output not in done:
                process.stdin.write((wait_code.result() + '\n').encode('ascii'))
                await process.stdin.drain()
                process.stdin.close()
                await output
            if await process.wait():
                raise ValueError('Claude sign-in failed')
        finally:
            for task in (output, wait_code):
                task.cancel()
            await asyncio.gather(output, wait_code, return_exceptions=True)


def cli(provider, cwd):
    home = Path.home()
    env = {name: os.environ[name] for name in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if name in os.environ}
    env['HOME'] = str(home)
    if provider == 'chatgpt':
        binary = os.getenv('OPEN_WEBUI_CODEX_BINARY') or shutil.which('codex') or home / '.local/bin/codex'
        if 'CODEX_HOME' in os.environ:
            env['CODEX_HOME'] = os.environ['CODEX_HOME']
        args = ('app-server', '--stdio', '-c', 'forced_login_method="chatgpt"')
    else:
        import pwd

        account = pwd.getpwuid(os.getuid())
        home = Path(account.pw_dir)
        binary = os.getenv('OPEN_WEBUI_CLAUDE_CODE_BINARY', str(home / '.local/bin/claude'))
        env.update(
            HOME=str(home), USER=account.pw_name, LOGNAME=account.pw_name, BROWSER='/usr/bin/false',
            CLAUDE_CONFIG_DIR=str(home / '.claude-open-webui'), ANTHROPIC_CONFIG_DIR=cwd,
        )
        args = ('auth', 'login', '--claudeai')
    if not Path(binary).is_absolute():
        raise ValueError('Expected an absolute CLI path')
    return binary, args, env


def official_url(value, hosts):
    if not isinstance(value, str) or not value.isascii() or len(value) > 4096 or re.search(r'[\s\\\x00-\x1f]', value):
        raise ValueError('Invalid sign-in URL')
    url = urlsplit(value)
    if url.scheme != 'https' or url.netloc not in hosts:
        raise ValueError('Invalid sign-in origin')
    return value


async def send(process, message):
    process.stdin.write(json.dumps(message).encode() + b'\n')
    await process.stdin.drain()


async def receive(process):
    line = await process.stdout.readline()
    if not line:
        raise ValueError('Codex login process ended')
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError('Invalid Codex message')
    return message


async def result(process, request_id):
    while True:
        message = await receive(process)
        if message.get('id') == request_id:
            reply = message.get('result')
            if not isinstance(reply, dict):
                raise ValueError('Codex login request failed')
            return reply
