"""Transactional owner-scoped portfolio persistence; no application payload logging."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Column, Integer, MetaData, String, Table, UniqueConstraint, create_engine, event, select, update, delete
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
portfolios = Table(
    "portfolios", metadata,
    Column("id", String, primary_key=True),
    Column("owner_id", String, nullable=False, index=True),
    Column("name", String, nullable=False),
    Column("positions", String, nullable=False),
    Column("revision", Integer, nullable=False, default=1),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("idempotency_key", String),
    UniqueConstraint("owner_id", "idempotency_key"),
)
users = Table("users", metadata, Column("id", String, primary_key=True), Column("email", String, nullable=False), Column("name", String, nullable=False))
schema_versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True), Column("applied_at", String, nullable=False))


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def encode(row):
    data = dict(row)
    data["positions"] = json.loads(data["positions"])
    data.pop("owner_id", None)
    data.pop("idempotency_key", None)
    return data


class PortfolioStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")

        self.migrate()

    def migrate(self):
        # v1 is an additive initial migration. Future versions must be explicit steps.
        with self.engine.begin() as conn:
            schema_versions.create(conn, checkfirst=True)
            current = conn.execute(select(schema_versions.c.version)).scalars().all()
            if any(v > 1 for v in current):
                raise RuntimeError("Database schema is newer than this application")
            if 1 not in current:
                users.create(conn, checkfirst=True)
                portfolios.create(conn, checkfirst=True)
                conn.execute(schema_versions.insert().values(version=1, applied_at=utc_now()))

    def remember_user(self, user):
        from sqlalchemy.dialects.sqlite import insert
        with self.engine.begin() as conn:
            stmt = insert(users).values(**user)
            conn.execute(stmt.on_conflict_do_update(index_elements=[users.c.id], set_={"email": user["email"], "name": user["name"]}))

    def list(self, owner):
        with self.engine.connect() as conn:
            return [encode(r) for r in conn.execute(select(portfolios).where(portfolios.c.owner_id == owner).order_by(portfolios.c.updated_at.desc())).mappings()]

    def get(self, owner, portfolio_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(portfolios).where(portfolios.c.owner_id == owner, portfolios.c.id == portfolio_id)).mappings().first()
        if row is None:
            raise NotFound()
        return encode(row)

    def create(self, owner, name, positions, key=None):
        now = utc_now()
        values = dict(id=str(uuid4()), owner_id=owner, name=name, positions=json.dumps(positions, sort_keys=True), revision=1, created_at=now, updated_at=now, idempotency_key=key)
        try:
            with self.engine.begin() as conn:
                conn.execute(portfolios.insert().values(**values))
        except IntegrityError:
            if not key:
                raise
            with self.engine.connect() as conn:
                row = conn.execute(select(portfolios).where(portfolios.c.owner_id == owner, portfolios.c.idempotency_key == key)).mappings().first()
            if row is None or row["name"] != name or row["positions"] != values["positions"]:
                raise Conflict("The retry key was already used for another portfolio")
            return encode(row)
        return encode(values)

    def update(self, owner, portfolio_id, name, positions, revision):
        with self.engine.begin() as conn:
            result = conn.execute(update(portfolios).where(portfolios.c.id == portfolio_id, portfolios.c.owner_id == owner, portfolios.c.revision == revision).values(name=name, positions=json.dumps(positions, sort_keys=True), revision=revision + 1, updated_at=utc_now()))
            if result.rowcount != 1:
                exists = conn.execute(select(portfolios.c.id).where(portfolios.c.id == portfolio_id, portfolios.c.owner_id == owner)).first()
                if not exists:
                    raise NotFound()
                raise Conflict("This portfolio changed in another session")
        return self.get(owner, portfolio_id)

    def delete(self, owner, portfolio_id, revision):
        with self.engine.begin() as conn:
            result = conn.execute(delete(portfolios).where(portfolios.c.id == portfolio_id, portfolios.c.owner_id == owner, portfolios.c.revision == revision))
            if result.rowcount != 1:
                exists = conn.execute(select(portfolios.c.id).where(portfolios.c.id == portfolio_id, portfolios.c.owner_id == owner)).first()
                if not exists:
                    raise NotFound()
                raise Conflict("This portfolio changed in another session")
