"""Actual Supabase Data API isolation checks, opt-in and local-only.

Run against a fresh CLI stack with QS_TEST_SUPABASE_URL, QS_TEST_SUPABASE_KEY
(publishable/anon) and QS_TEST_SUPABASE_ADMIN_KEY supplied in the environment.
Never run this synthetic-user fixture against a hosted/production project.
"""
import os
import subprocess
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest

URL = os.getenv('QS_TEST_SUPABASE_URL', '')
KEY = os.getenv('QS_TEST_SUPABASE_KEY', '')
ADMIN = os.getenv('QS_TEST_SUPABASE_ADMIN_KEY', '')
DB_CONTAINER = os.getenv('QS_TEST_SUPABASE_DB_CONTAINER', '')
pytestmark = pytest.mark.skipif(not all((URL, KEY, ADMIN, DB_CONTAINER)), reason='Local Supabase integration environment is not configured')


def admit(user_id, active):
    # Synthetic UUIDs created by this fixture, never user-supplied SQL. Admission
    # uses the isolated DB operator channel; market service_role has no grant.
    from uuid import UUID
    uid = str(UUID(user_id))
    if not DB_CONTAINER.startswith('supabase_db_'):
        pytest.fail('Expected a local Supabase test container')
    sql = f"insert into public.app_members(user_id,active) values('{uid}',{str(active).lower()}) on conflict(user_id) do update set active=excluded.active;"
    result = subprocess.run(['docker','exec','-i',DB_CONTAINER,'psql','-U','postgres','-d','postgres','-v','ON_ERROR_STOP=1'],input=sql,text=True,capture_output=True)
    assert result.returncode == 0, 'Test admission SQL failed'


@pytest.fixture
def accounts():
    parsed = urlparse(URL)
    if parsed.hostname not in ('127.0.0.1', 'localhost'):
        pytest.fail('Integration fixtures are restricted to an isolated local Supabase stack')
    users = []
    clients = []
    admin_headers = {'apikey': ADMIN}
    if ADMIN.startswith('eyJ'):
        admin_headers['Authorization'] = 'Bearer ' + ADMIN
    admin = httpx.Client(base_url=URL, headers=admin_headers,timeout=15)
    try:
        for active in (True, True, False):
            email, password = f'qs-test-{uuid4().hex}@example.test', uuid4().hex+'Aa1!'
            response = admin.post('/auth/v1/admin/users',json={'email':email,'password':password,'email_confirm':True})
            assert response.status_code in (200,201), 'Test user provisioning failed'
            uid = response.json()['id']
            users.append(uid)
            admit(uid, active)
            login = httpx.post(URL+'/auth/v1/token?grant_type=password',headers={'apikey':KEY},json={'email':email,'password':password},timeout=15)
            assert login.status_code == 200, 'Test login failed'
            clients.append(httpx.Client(base_url=URL,headers={'apikey':KEY,'Authorization':'Bearer '+login.json()['access_token']},timeout=15))
        yield admin, users, clients
    finally:
        for client in clients:
            client.close()
        for uid in users:
            admin.delete('/auth/v1/admin/users/'+uid)
        admin.close()


def command(client, action, **values):
    body = dict(p_action=action,p_id=None,p_name=None,p_positions=None,p_revision=None,p_key=None)
    body.update(values)
    return client.post('/rest/v1/rpc/portfolio_command',json=body)


def test_real_rls_ownership_revision_and_direct_write_guards(accounts):
    admin, users, (a,b,c) = accounts
    positions = [{'symbol':'MSFT','weight_bps':4500}]
    payload = dict(p_name='Private draft',p_positions=positions,p_key='retry-'+uuid4().hex)
    first = command(a,'create',**payload)
    assert first.status_code == 200
    saved = first.json()
    pid = saved['id']
    assert command(a,'create',**payload).json() == saved
    assert command(a,'create',**{**payload,'p_name':'Changed'}).status_code == 409
    for outsider in (b,c):
        assert outsider.get('/rest/v1/portfolios',params={'id':'eq.'+pid}).json() == []
        assert outsider.get('/rest/v1/portfolio_positions',params={'portfolio_id':'eq.'+pid}).json() == []
        assert command(outsider,'get',p_id=pid).status_code in (403,404)
        assert command(outsider,'delete',p_id=pid,p_revision=1).status_code in (403,404)
    assert command(c,'create',**payload).status_code == 403
    assert a.patch('/rest/v1/portfolios',params={'id':'eq.'+pid},json={'name':'Bypass'}).status_code == 403
    assert a.patch('/rest/v1/portfolio_positions',params={'portfolio_id':'eq.'+pid},json={'weight_bps':10000}).status_code == 403
    assert b.post('/rest/v1/portfolio_positions',json={'portfolio_id':pid,'owner_id':users[1],'symbol':'AAPL','weight_bps':10,'ordinal':2}).status_code in (403,409)
    updated = command(a,'update',p_id=pid,p_name='Updated',p_positions=positions,p_revision=1)
    assert updated.status_code == 200 and updated.json()['revision'] == 2
    assert command(a,'update',p_id=pid,p_name='Stale',p_positions=positions,p_revision=1).status_code == 409
    assert command(a,'delete',p_id=pid,p_revision=1).status_code == 409
    # Constraint failure must roll back both name/revision and child positions.
    invalid = command(a,'update',p_id=pid,p_name='Invalid',p_positions=positions*2,p_revision=2)
    assert invalid.status_code == 422
    assert command(a,'get',p_id=pid).json()['name'] == 'Updated'
    assert admin.patch('/rest/v1/app_members',params={'user_id':'eq.'+users[0]},json={'active':False}).status_code in (401,403)
    admit(users[0], False)
    assert a.get('/rest/v1/portfolios').json() == []
    assert command(a,'get',p_id=pid).status_code == 403
    anonymous = httpx.get(URL+'/rest/v1/portfolios',headers={'apikey':KEY},timeout=15)
    assert anonymous.status_code in (401,403)
