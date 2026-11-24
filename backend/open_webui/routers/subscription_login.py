import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from open_webui.env import ENABLE_FUNCTIONS, WEBUI_AUTH
from open_webui.utils.auth import get_admin_user
from open_webui.utils.subscription_login import LoginAttempt


Provider = Literal['chatgpt', 'claude']
router = APIRouter(dependencies=[Depends(get_admin_user)])
attempts: dict[str, LoginAttempt] = {}


def enabled():
    return WEBUI_AUTH and ENABLE_FUNCTIONS and os.getenv('ENABLE_PERSONAL_SUBSCRIPTION_LOGIN', '').lower() == 'true'


def response(data):
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


def owned_attempt(provider, attempt_id, user):
    attempt = attempts.get(provider)
    if not enabled() or not attempt or attempt.id != attempt_id or attempt.owner != user.id:
        raise HTTPException(404, 'Sign-in attempt not found. Start again.')
    return attempt


@router.get('/availability')
async def availability():
    return response({'enabled': enabled()})


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
    attempt.start()
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
