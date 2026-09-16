import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
import pytest

from data_engine.freshness import FreshnessPolicy
from data_engine.service import DataService
from data_engine.supabase_cache import RemoteCacheError, SupabaseMarketCache


@pytest.fixture
def remote():
    state = {'records': {}, 'objects': {}, 'events': [], 'publish': True, 'lease': True, 'corrupt': False, 'upload_fail': False}
    def handle(request):
        state['events'].append((request.method, request.url.path))
        assert request.headers['apikey'] == 'market-test-only'
        path = request.url.path
        if path.endswith('claim_market_refresh_lease'):
            return httpx.Response(200, json={'lease_token':'123', 'lease_fence':1,'lease_expires_at':'2099-01-01T00:00:00Z'} if state['lease'] else None)
        if path.endswith('publish_market_dataset'):
            body = json.loads(request.content)
            if state['publish']:
                state['records'][body['p_dataset_key']] = body['p_record']
            return httpx.Response(200, json=state['publish'])
        if path.endswith('market_data_metadata'):
            record = state['records'].get(request.url.params['dataset_key'][3:])
            return httpx.Response(200,json=[{'record':record}] if record else [])
        if request.method == 'POST':
            if state['upload_fail']:
                return httpx.Response(503)
            state['objects'][path] = request.content
            return httpx.Response(200,json={})
        payload = state['objects'].get(path)
        return httpx.Response(200, content=b'corrupt' if state['corrupt'] else payload) if payload else httpx.Response(404)
    cache = SupabaseMarketCache('https://project.supabase.co','market-test-only',transport=httpx.MockTransport(handle))
    yield cache, state
    cache.close()


def test_roundtrip_and_verified_publication(remote):
    cache, state = remote
    frame = pd.DataFrame({'close':[100.,101.],'volume':[5.,6.]}, index=pd.date_range('2026-01-01',periods=2,tz='UTC'))
    with cache.refresh_lease('history:MSFT') as acquired:
        assert acquired
        cache.put_history('history:MSFT',frame,{'source':'fixture','status':'fresh'})
    restored = cache.get_history('history:MSFT')
    pd.testing.assert_frame_equal(restored.frame,frame,check_freq=False)
    events = state['events']
    upload = next(i for i, (method,path) in enumerate(events) if method=='POST' and '/storage/' in path)
    assert events[upload+1][0] == 'GET'
    assert events[upload+2][1].endswith('publish_market_dataset')
    record = state['records']['history:MSFT']
    assert len(record['checksum_sha256']) == 64
    state['corrupt'] = True
    assert cache.get_history('history:MSFT') is None
    state['corrupt'] = False
    state['objects'].clear()
    assert cache.get_history('history:MSFT') is None


def test_failures_never_replace_last_valid_pointer(remote):
    cache, state = remote
    key = 'fred:DGS10'
    with cache.refresh_lease(key):
        cache.put_value(key,{'rate':0.04})
    first = state['records'][key].copy()
    for failure in ('upload_fail','corrupt'):
        state[failure] = True
        with cache.refresh_lease(key), pytest.raises(RemoteCacheError):
            cache.put_value(key, {'rate':0.05})
        assert state['records'][key] == first
        state[failure] = False
    state['publish'] = False
    with cache.refresh_lease(key), pytest.raises(RemoteCacheError):
        cache.put_value(key,{'rate':0.06})
    assert state['records'][key] == first
    assert cache.get_value(key)[0]['rate'] == 0.04
    with pytest.raises(RemoteCacheError,match='lease'):
        cache.put_value(key,{'rate':0.07})


def test_remote_service_no_local_state_and_busy_lease(remote,tmp_path,monkeypatch):
    cache, state = remote
    service = DataService(tmp_path/'must-not-exist','research',cache=cache)
    assert service.instrument('MSFT')['sector'] == 'Information Technology'
    state['lease'] = False
    monkeypatch.setattr(service,'_yahoo_history',lambda *_: pytest.fail('Must not duplicate another refresher'))
    assert service.get_history('MSFT').meta['status'] == 'unavailable'
    assert service.get_fundamentals('MSFT')['meta']['status'] == 'unavailable'
    assert service.risk_free_rate()['rate'] is None
    assert not service.refresh_universe()
    assert not (tmp_path/'must-not-exist').exists()


def test_freshness_rejects_future_or_naive_timestamps():
    now = datetime(2026,1,1,tzinfo=timezone.utc)
    policy = FreshnessPolicy(clock=lambda:now)
    assert policy.is_fresh(now,timedelta(minutes=5))
    assert not policy.is_fresh(now+timedelta(seconds=1),timedelta(minutes=5))
    assert not policy.is_fresh(now.replace(tzinfo=None),timedelta(minutes=5))


@pytest.mark.parametrize('key, bearer', [('sb_secret_market_only', None), ('eyJlegacy.jwt.signature', 'Bearer eyJlegacy.jwt.signature')])
def test_secret_key_transport_does_not_masquerade_as_user_jwt(key, bearer):
    def handle(request):
        assert request.headers['apikey'] == key
        assert request.headers.get('authorization') == bearer
        return httpx.Response(200, json=[])
    cache = SupabaseMarketCache('https://project.supabase.co', key, transport=httpx.MockTransport(handle))
    try:
        assert cache.get_value('missing') is None
    finally:
        cache.close()


def test_universe_publication_normalizes_sector_contract(remote):
    cache, state = remote
    payload = {'items':[{'symbol':'BRK.B','name':'Berkshire','gics_sector':'Financials'}]}
    with cache.refresh_lease('universe:sp500'):
        cache.put_value('universe:sp500',payload)
    assert state['records']['universe:sp500']['constituents'] == [
        {'symbol':'BRK-B','name':'Berkshire','sector':'Financials'}]
