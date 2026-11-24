import asyncio
import logging
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from open_webui.env import ENABLE_FUNCTIONS, SAFE_MODE, WEBUI_AUTH
from open_webui.models.functions import FunctionForm, FunctionMeta, Functions
from open_webui.models.users import Users
from open_webui.utils import chatgpt_subscription_pipe, claude_subscription_pipe
from open_webui.utils.auth import get_admin_user
from open_webui.utils.subscription_login import LoginAttempt


Provider = Literal['chatgpt', 'claude']
router = APIRouter(dependencies=[Depends(get_admin_user)])
attempts: dict[str, LoginAttempt] = {}
providers = {
    'chatgpt': ('ChatGPT Subscription (Personal, via Codex CLI)', chatgpt_subscription_pipe),
    'claude': ('Claude Subscription (Personal)', claude_subscription_pipe),
}
model_locks = {provider: asyncio.Lock() for provider in providers}
log = logging.getLogger(__name__)


def enabled():
    return (
        WEBUI_AUTH and ENABLE_FUNCTIONS and not SAFE_MODE
        and os.getenv('ENABLE_PERSONAL_SUBSCRIPTION_LOGIN', '').lower() == 'true'
    )


def response(data):
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


def owned_attempt(provider, attempt_id, user):
    attempt = attempts.get(provider)
    if not enabled() or not attempt or attempt.id != attempt_id or attempt.owner != user.id:
        raise HTTPException(404, 'Sign-in attempt not found. Start again.')
    return attempt


async def sync_connection(request, user, provider):
    name, module = providers[provider]
    previous_models = module.subscription_models()
    try:
        models = await module.refresh_subscription_models()
    except chatgpt_subscription_pipe.ModelCatalogError as exc:
        return {'connected': True, 'model_id': None, 'detail': str(exc)}
    except (PermissionError, RuntimeError) as exc:
        return {'connected': False, 'model_id': None, 'detail': str(exc)}
    if not models:
        return {'connected': True, 'model_id': None, 'detail': 'The provider did not list any available text models.'}

    model_id = f'{provider}_subscription'
    # Store a normal Pipe entry, with implementation updates picked up from the installed backend.
    content = f'from {module.__name__} import Pipe\n'
    try:
        async with model_locks[provider]:
            function = await Functions.get_function_by_id(model_id)
            if function is None:
                function = await Functions.insert_new_function(
                    user.id, 'pipe', FunctionForm(
                        id=model_id, name=name, content=content,
                        meta=FunctionMeta(description='Private text chat through the official subscription CLI.'),
                    ), is_active=True,
                )
                previous_models = ()
            elif function.type != 'pipe' or function.content != content:
                detail = f'A custom Function uses the ID {model_id}. Back it up and remove it to install the built-in model.'
                return {'connected': True, 'model_id': None, 'detail': detail}
            if models != previous_models:
                from open_webui.utils.models import BASE_MODELS_CACHE_KEY

                request.app.state.BASE_MODELS = []
                if request.app.state.redis is not None:
                    await request.app.state.redis.delete(BASE_MODELS_CACHE_KEY)
    except Exception:
        log.exception('Could not provision the %s subscription model', provider)
        return {'connected': True, 'model_id': None, 'detail': 'Could not enable the model. Reload this page to retry.'}
    if not function.is_active:
        return {'connected': True, 'model_id': None, 'detail': 'The model is disabled. Enable its Function below.'}
    return {'connected': True, 'model_id': f'{model_id}.{models[0]["id"]}', 'detail': None}


async def restore_models(request):
    if enabled():
        user = await Users.get_first_user()
        if user and user.role == 'admin':
            await asyncio.gather(*(sync_connection(request, user, provider) for provider in providers))


@router.post('/sync')
async def sync(request: Request, user=Depends(get_admin_user)):
    if not enabled():
        return response({'enabled': False})

    async def provider_state(provider):
        attempt = attempts.get(provider)
        if attempt and attempt.task and not attempt.task.done():
            return {'attempt': attempt.public() if attempt.owner == user.id else None, 'connection': None}
        return {'attempt': None, 'connection': await sync_connection(request, user, provider)}

    return response({'enabled': True, 'providers': dict(zip(
        providers, await asyncio.gather(*(provider_state(provider) for provider in providers)),
    ))})


@router.post('/{provider}')
async def start(provider: Provider, request: Request, user=Depends(get_admin_user)):
    if request.headers.get('content-type') != 'application/json':
        raise HTTPException(415, 'Expected a JSON sign-in request.')
    if not enabled():
        raise HTTPException(404, 'Personal subscription sign-in is disabled.')
    previous = attempts.get(provider)
    if previous and previous.task and not previous.task.done():
        if previous.owner != user.id:
            raise HTTPException(409, 'A sign-in attempt is already running.')
        return response(previous.public())
    attempt = LoginAttempt(user.id, provider)
    attempts[provider] = attempt
    attempt.start(lambda: sync_connection(request, user, provider))
    return response(attempt.public())


@router.get('/{provider}/{attempt_id}')
async def status(provider: Provider, attempt_id: str, user=Depends(get_admin_user)):
    return response(owned_attempt(provider, attempt_id, user).public())


@router.delete('/{provider}/{attempt_id}')
async def cancel(provider: Provider, attempt_id: str, user=Depends(get_admin_user)):
    attempt = owned_attempt(provider, attempt_id, user)
    if attempt.task and not attempt.task.done():
        attempt.task.cancel()
        attempt.state = 'cancelled'
        attempt.url = attempt.device_code = None
    return response(attempt.public())


@router.post('/claude/{attempt_id}/code')
async def submit_claude_code(attempt_id: str, request: Request, user=Depends(get_admin_user)):
    attempt = owned_attempt('claude', attempt_id, user)
    if request.headers.get('content-type') != 'application/octet-stream':
        raise HTTPException(415, 'Expected a one-time Claude login code.')
    code = bytearray()
    async for chunk in request.stream():
        if len(code) + len(chunk) > 2048:
            raise HTTPException(400, 'Invalid Claude login code.')
        code.extend(chunk)
    code = code.strip()
    if not code or not all(33 <= char <= 126 for char in code):
        raise HTTPException(400, 'Use only the one-time login code shown by Claude.')
    if attempt.state != 'waiting':
        raise HTTPException(409, 'This attempt is not waiting for a code. Refresh its status.')
    attempt.code.put_nowait(code.decode('ascii'))
    attempt.state = 'verifying'
    attempt.url = None
    return response(attempt.public())
