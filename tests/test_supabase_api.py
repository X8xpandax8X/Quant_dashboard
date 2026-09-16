"""Network-free adapter tests; actual RLS checks are a separate integration suite."""
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from data_engine.service import DataService

A = str(uuid4())
B = str(uuid4())
ORIGIN = 'https://research.example'


def settings(tmp_path, **kwargs):
    return Settings(mode='research', backend='supabase', storage_dir=tmp_path/'private',
                    public_origin=ORIGIN, supabase_url='https://project.supabase.co',
                    supabase_publishable_key='sb_publishable_test', csrf_secret='s'*40,
                    allowed_emails='a@example.com,b@example.com', _env_file=None, **kwargs)


@pytest.fixture
def remote(tmp_path):
    state = {'active': True, 'provider': 'google', 'calls': [], 'rpc_code': None, 'auth_status': 200}
    def handle(request):
        state['calls'].append(request)
        assert request.headers['apikey'] == 'sb_publishable_test'
        assert request.headers['authorization'] in ('Bearer token-a', 'Bearer token-b', 'Bearer expired')
        uid = B if request.headers['authorization'] == 'Bearer token-b' else A
        if request.url.path == '/auth/v1/user':
            return httpx.Response(state['auth_status'], json={
                'id': uid, 'email': 'b@example.com' if uid == B else 'a@example.com',
                'email_confirmed_at': '2026-01-01', 'app_metadata': {'providers': [state['provider']]},
                'user_metadata': {'provider': 'google', 'active': True},
            })
        if request.url.path == '/rest/v1/app_members':
            return httpx.Response(200, json=[{'user_id': uid}] if state['active'] else [])
        if request.url.path == '/auth/v1/logout':
            return httpx.Response(204)
        assert request.url.path == '/rest/v1/rpc/portfolio_command'
        body = json.loads(request.content)
        assert not any(k in body for k in ('owner_id', 'user_id'))
        if state['rpc_code']:
            return httpx.Response(400, json={'code': state['rpc_code'], 'message': 'DO NOT EXPOSE'})
        return httpx.Response(200, json=[])
    config = settings(tmp_path)
    app = create_app(config, DataService(tmp_path/'demo-cache', 'demo'), supabase_transport=httpx.MockTransport(handle))
    with TestClient(app) as client:
        yield client, state, config
    assert not config.storage_dir.exists(), 'Supabase user path must not create a local state database'


def test_supabase_auth_fails_closed_and_ignores_spoofed_headers(remote):
    client, state, _ = remote
    assert client.get('/api/v1/auth/me', headers={'x-auth-user': A, 'x-auth-email': 'a@example.com', 'x-proxy-secret': 's'*40}).status_code == 401
    assert state['calls'] == []
    h = {'Authorization': 'Bearer token-a'}
    assert client.get('/api/v1/auth/me', headers=h).json()['user']['id'] == A
    state['provider'] = 'email'
    assert client.get('/api/v1/auth/me', headers=h).status_code == 403
    state['provider'] = 'google'
    state['active'] = False
    assert client.get('/api/v1/auth/me', headers=h).status_code == 403
    state['active'] = True
    state['auth_status'] = 401
    assert client.get('/api/v1/auth/me', headers=h).status_code == 401


def test_user_context_is_request_scoped_and_revocation_rechecked(remote):
    client, state, _ = remote
    for token in ('token-a', 'token-b', 'token-a'):
        assert client.get('/api/v1/portfolios', headers={'Authorization': 'Bearer '+token}).status_code == 200
        assert state['calls'][-1].headers['authorization'] == 'Bearer '+token
    state['active'] = False
    assert client.get('/api/v1/portfolios', headers={'Authorization':'Bearer token-a'}).status_code == 403


def test_csrf_and_error_mapping(remote):
    client, state, _ = remote
    h = {'Authorization': 'Bearer token-a'}
    csrf = client.get('/api/v1/auth/me', headers=h).json()['csrf_token']
    payload = {'name': 'Private draft', 'positions':[{'symbol':'MSFT','weight_bps':1000}]}
    url = '/api/v1/portfolios'
    assert client.post(url, json=payload, headers=h).status_code == 403
    h.update({'Origin':ORIGIN, 'X-CSRF-Token':csrf})
    assert client.post(url, json=payload, headers={**h,'Origin':'https://evil.example'}).status_code == 403
    for code, expected in [('PT409',409),('PT404',404),('PT422',422),('unknown',503)]:
        state['rpc_code'] = code
        response = client.post(url, json=payload, headers=h)
        assert response.status_code == expected
        assert 'DO NOT EXPOSE' not in response.text
    assert client.post('/api/v1/auth/logout', headers=h).status_code == 204


def test_configuration_refuses_privileged_user_key(tmp_path):
    config = settings(tmp_path)
    for key in ('sb_secret_bad', 'legacy.jwt.key', ''):
        config.supabase_publishable_key = key
        with pytest.raises(RuntimeError, match='publishable'):
            config.check()
