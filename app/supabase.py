"""Request-scoped user access. This module never accepts a service-role key."""
from uuid import UUID

import httpx
from fastapi import HTTPException


class UserDataClient:
    def __init__(self, settings, token: str, transport=None):
        self.url = settings.supabase_url.rstrip('/')
        self.key = settings.supabase_publishable_key
        self._token = token
        self.transport = transport

    def request(self, method, path, **kwargs):
        try:
            with httpx.Client(transport=self.transport, timeout=15, follow_redirects=False) as client:
                response = client.request(method, self.url + path, headers={
                    'apikey': self.key, 'Authorization': 'Bearer ' + self._token,
                    'Accept': 'application/json',
                }, **kwargs)
        except httpx.HTTPError:
            raise HTTPException(503, 'Account service is temporarily unavailable') from None
        if response.status_code == 401:
            raise HTTPException(401, 'Sign in to continue')
        if response.status_code == 403:
            raise HTTPException(403, 'This account cannot access the requested resource')
        if response.status_code >= 500:
            raise HTTPException(503, 'Account service is temporarily unavailable')
        return response

    def authenticate(self, allowlist):
        # /user validates the JWT with this project's Auth server. Never trust a
        # decoded token, proxy identity header or user-editable user_metadata.
        response = self.request('GET', '/auth/v1/user')
        if response.status_code != 200:
            raise HTTPException(401, 'Sign in to continue')
        try:
            raw = response.json()
            user_id = str(UUID(raw['id']))
            email = raw['email'].strip().lower()
            providers = raw.get('app_metadata', {}).get('providers', [])
            if (raw.get('is_anonymous') or not raw.get('email_confirmed_at')
                    or email not in allowlist or 'google' not in providers):
                raise ValueError('Not an admitted Google identity')
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(403, 'This account is not on the team allowlist') from None
        membership = self.request('GET', '/rest/v1/app_members', params={
            'select': 'user_id', 'user_id': 'eq.' + user_id, 'active': 'eq.true',
        })
        if membership.status_code != 200:
            raise HTTPException(503, 'Team admission could not be checked')
        try:
            rows = membership.json()
            admitted = isinstance(rows, list) and any(row.get('user_id') == user_id for row in rows)
        except (ValueError, TypeError, AttributeError):
            admitted = False
        if not admitted:
            raise HTTPException(403, 'This account is not an active team member')
        return {'id': user_id, 'email': email, 'name': email.split('@')[0]}

    def logout(self):
        response = self.request('POST', '/auth/v1/logout', params={'scope': 'local'})
        if response.status_code not in (200, 204):
            raise HTTPException(503, 'Sign out could not be completed. Please retry.')
