from uuid import UUID

from fastapi import HTTPException

from app.db import Conflict, NotFound


class SupabasePortfolioStore:
    """Request-scoped repository: no owner parameter and no privileged credentials.

    Identity is derived by Postgres auth.uid(); the caller cannot submit an owner.
    All mutations use one invoker RPC transaction, including positions and retries.
    """
    def __init__(self, client):
        self.client = client

    def call(self, action, *, portfolio_id=None, name=None, positions=None, revision=None, key=None):
        if portfolio_id is not None:
            try:
                portfolio_id = str(UUID(portfolio_id))
            except ValueError:
                raise NotFound() from None
        response = self.client.request('POST', '/rest/v1/rpc/portfolio_command', json={
            'p_action': action, 'p_id': portfolio_id, 'p_name': name,
            'p_positions': positions, 'p_revision': revision, 'p_key': key,
        })
        if response.status_code >= 400:
            try:
                code = response.json().get('code')
            except ValueError:
                code = None
            if code == 'PT404':
                raise NotFound()
            if code in ('PT409', '23505'):
                raise Conflict('This portfolio changed, or the retry key has already been used')
            if code in ('PT422', '23514', '22P02'):
                raise HTTPException(422, 'Invalid portfolio data')
            raise HTTPException(503, 'Portfolio service is temporarily unavailable')
        return response.json() if response.content else None

    def list(self):
        return self.call('list')

    def get(self, portfolio_id):
        return self.call('get', portfolio_id=portfolio_id)

    def create(self, name, positions, key=None):
        return self.call('create', name=name, positions=positions, key=key)

    def update(self, portfolio_id, name, positions, revision):
        return self.call('update', portfolio_id=portfolio_id, name=name, positions=positions, revision=revision)

    def delete(self, portfolio_id, revision):
        self.call('delete', portfolio_id=portfolio_id, revision=revision)
