"""Schema-per-target mechanics, shared by every Postgres-backed `TargetHolding` — ledger task
**R34.8**, factored out of `weft_store.pgvector_store.PgVectorStore` (task **34.1**) and a second
store elsewhere in this wheel that grew an identical target machinery of its own a few tasks
later, differing only in a schema/lock-key prefix, which two catalogue tables it keeps, which
tables belong to one target, and which error class a missing table raises. `PgTargetLayout` below
is that difference, made a value instead of a second copy of the code around it.

**One schema per target, reached through `search_path`, never a rewrite of a store's own
unqualified statements.** `default` is the pre-target tables in the connection's own home
schema — `current_schema()`, read once before `search_path` ever moves — so a database written
before targets existed reads as `default`, live, with no operator action. Any other target
`<name>` is `<layout.schema_prefix><name>`; a handle bound to one sets `search_path = <schema>,
<home schema>`, home schema kept second so the extension operators a store's own unqualified
statements rely on (`vector`'s `<=>`, `pg_trgm`'s `similarity`) keep resolving — measured
(ledger `34.0`) to fall through silently to `default`'s own table of the same name the moment it
is dropped from the path. The catalogue — which targets exist, which is live, the embedding
identity each claimed — lives in two tables in the home schema, always reached schema-qualified
regardless of which target's schema is currently on the path, so a candidate's own `search_path`
never decides which catalogue a caller reads. **A catalogued target whose table has gone missing
is refused by name, through `layout.missing_table_error`, rather than silently re-provisioned
empty or read through to `default`'s table of the same name** — the fall-through `34.0` measured
and task 34.1 closed. Every handle bound to a non-default target holds `pg_advisory_lock_shared`
on it for the connection's lifetime, so `drop_target` on a target another handle is using fails
loudly instead of dropping a schema a live statement is about to read.

**Depends on `weft_store.contract` only, and names no other pack in this wheel** — fitness
function 28(c)'s own rule, applied to this module: the second store above already imports from
`weft_store`, and this module keeps that direction rather than opening a new one back.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from weft_kernel.errors import WeftError
from weft_store.contract import (
    DEFAULT_TARGET,
    EmbeddingIdentity,
    NoPreviousTargetError,
    Promotion,
    TargetCatalogue,
    TargetInUseError,
    TargetName,
    TargetRecord,
    UnknownTargetError,
)


@dataclass(frozen=True, slots=True)
class PgTargetLayout:
    """One store's own naming for the schema-per-target mechanics — the only thing that differs
    between `weft_store.pgvector_store.PgVectorStore` and the second store above that shares
    this module.
    """

    #: A target's schema is `f"{schema_prefix}{target}"` — `weft_target_` / `kg_target_`.
    schema_prefix: str
    #: A target's advisory lock key is `f"{lock_key_prefix}{target}"` — distinct per store so two
    #: packs' locks never collide when both dsns name the same database.
    lock_key_prefix: str
    #: The catalogue table naming every target this store has ever written to, and the embedding
    #: identity claimed against it, if any.
    targets_table: str
    #: The one-row table naming which target is live, which was live before that, and the
    #: `Promotion` that made it so.
    live_target_table: str
    #: Every table one target holds — what `verify_target_tables` checks for on a catalogued
    #: target, and what `drop_target` removes when the target being dropped is `default`.
    target_tables: tuple[str, ...]
    #: Builds this store's own missing-table refusal from the shared message text — a plain
    #: `WeftError` subclass with no custom `__init__`, so a `lambda message: SomeError(message,
    #: pack="...")` is the whole of what a store supplies.
    missing_table_error: Callable[[str], WeftError]


def target_schema(layout: PgTargetLayout, target: TargetName) -> sql.Identifier:
    """A target's own schema, composed with `sql.Identifier` rather than string formatting —
    never interpolated from anything but a `TargetName`, which `weft_store.contract.target_name`
    has already checked against a closed grammar before a caller ever reaches a store.
    """
    return sql.Identifier(f"{layout.schema_prefix}{target}")


def home_table(home_schema: str, table: str) -> sql.Composed:
    """`<home_schema>.<table>`, composed of two `sql.Identifier`s — every catalogue statement's
    own qualification, so a candidate's own `search_path` never decides which catalogue a read
    means.
    """
    return sql.SQL(".").join([sql.Identifier(home_schema), sql.Identifier(table)])


def lock_key(layout: PgTargetLayout, target: TargetName) -> str:
    """What `hashtext()` turns into this target's advisory lock key — never `0`, the sentinel
    Postgres's own `pg_advisory_lock` family treats no differently, but a key worth reading in a
    `pg_locks` row beats an opaque integer.
    """
    return f"{layout.lock_key_prefix}{target}"


def create_targets_table_sql(layout: PgTargetLayout, home_schema: str) -> sql.Composed:
    """The catalogue table — `default` needs no row in it, since `target_catalogue` lists it
    regardless, so it only ever holds a target `bind_target` was asked for by name.
    """
    return sql.SQL(
        "CREATE TABLE IF NOT EXISTS {} ("
        "name TEXT PRIMARY KEY, embedding JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    ).format(home_table(home_schema, layout.targets_table))


def create_live_target_table_sql(layout: PgTargetLayout, home_schema: str) -> sql.Composed:
    """The one-row live-pointer table.

    `singleton` is checked rather than merely a primary key of one value, so a second row is refused
    by the schema itself rather than by convention.
    """
    return sql.SQL(
        "CREATE TABLE IF NOT EXISTS {} ("
        "singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton), "
        "live TEXT NOT NULL, previous TEXT, promotion JSONB)"
    ).format(home_table(home_schema, layout.live_target_table))


async def read_live_target(
    layout: PgTargetLayout, conn: "psycopg.AsyncConnection[dict[str, Any]]", home_schema: str
) -> TargetName:
    """The live target the live-pointer table names, or `DEFAULT_TARGET` when it holds no row
    yet — the upgrade clause: a database written before targets existed reads as `default`, live,
    with no operator action.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SELECT live FROM {}").format(home_table(home_schema, layout.live_target_table))
        )
        row = await cur.fetchone()
    return TargetName(cast(str, row["live"])) if row is not None else DEFAULT_TARGET


async def verify_target_tables(
    layout: PgTargetLayout, conn: "psycopg.AsyncConnection[dict[str, Any]]", target: TargetName
) -> None:
    """Refuse `target` by name the moment one of its own tables is gone, rather than let
    `search_path` quietly resolve the bare name to `default`'s own table.
    """
    schema_name = f"{layout.schema_prefix}{target}"
    for table in layout.target_tables:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT to_regclass(%s) IS NULL AS missing", (f"{schema_name}.{table}",)
            )
            row = await cur.fetchone()
        if row is not None and row["missing"]:
            raise layout.missing_table_error(
                f"target {target!r} is catalogued, but its table {table} is missing from "
                f"schema {schema_name} — something outside Weft dropped it, or a drop was "
                f"interrupted. Weft will not recreate it empty or read another target's "
                f"table in its place. Drop the target and index it again."
            )


async def enter_target_schema(
    layout: PgTargetLayout,
    conn: "psycopg.AsyncConnection[dict[str, Any]]",
    home_schema: str,
    target: TargetName,
) -> None:
    """Reach `target`'s own tables through `search_path`, without rewriting a single one of a
    store's own unqualified statements.

    A catalogued target's tables must already exist (`verify_target_tables` refuses by name,
    never recreates); an uncatalogued one is a candidate about to be written for the first time,
    and gets a fresh schema. Either way the schema is entered by `search_path`, home schema kept
    on it second so a store's own extension operators keep resolving.
    """
    schema = target_schema(layout, target)
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SELECT 1 AS present FROM {} WHERE name = %s").format(
                home_table(home_schema, layout.targets_table)
            ),
            (target,),
        )
        catalogued = await cur.fetchone() is not None
    if catalogued:
        await verify_target_tables(layout, conn, target)
    else:
        async with conn.cursor() as cur:
            await cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SET search_path = {}, {}").format(schema, sql.Identifier(home_schema))
        )
        await cur.execute(
            "SELECT pg_advisory_lock_shared(hashtext(%s))", (lock_key(layout, target),)
        )


async def resolve_active_target(
    layout: PgTargetLayout,
    conn: "psycopg.AsyncConnection[dict[str, Any]]",
    home_schema: str,
    bound: TargetName | None,
) -> TargetName:
    """Create the catalogue tables if needed, resolve `bound` or the live target, and enter its
    schema when it is not `default`.

    The common tail of both stores' own `_connection`: called once each has opened its
    connection, read `home_schema` from `current_schema()`, created its own extensions and
    registered the vector adapter — all of which must run while `search_path` is still the
    connection's own default, never after a target has put another schema ahead of it, or a
    first-ever connection bound straight to a candidate target would create an extension's
    objects inside that target's schema instead of the home one.
    """
    async with conn.cursor() as cur:
        await cur.execute(create_targets_table_sql(layout, home_schema))
        await cur.execute(create_live_target_table_sql(layout, home_schema))
    target = bound if bound is not None else await read_live_target(layout, conn, home_schema)
    if target != DEFAULT_TARGET:
        await enter_target_schema(layout, conn, home_schema, target)
    return target


async def register_target_if_needed(
    layout: PgTargetLayout,
    cur: "psycopg.AsyncCursor[dict[str, Any]]",
    *,
    target: TargetName | None,
    home_schema: str | None,
) -> None:
    """The catalogue row a non-default target earns on its first write — never on a bind, never
    on a read. `default` needs none: the catalogue lists it regardless.
    """
    if target is None or target == DEFAULT_TARGET or home_schema is None:
        return
    await cur.execute(
        sql.SQL("INSERT INTO {} (name) VALUES (%s) ON CONFLICT (name) DO NOTHING").format(
            home_table(home_schema, layout.targets_table)
        ),
        (target,),
    )


async def target_catalogue(
    layout: PgTargetLayout, conn: "psycopg.AsyncConnection[dict[str, Any]]", home_schema: str
) -> TargetCatalogue:
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SELECT live, previous, promotion FROM {}").format(
                home_table(home_schema, layout.live_target_table)
            )
        )
        live_row = await cur.fetchone()
        await cur.execute(
            sql.SQL("SELECT name, embedding FROM {} ORDER BY name").format(
                home_table(home_schema, layout.targets_table)
            )
        )
        target_rows = await cur.fetchall()
    live = TargetName(cast(str, live_row["live"])) if live_row is not None else DEFAULT_TARGET
    previous = live_row["previous"] if live_row is not None else None
    promotion_json = live_row["promotion"] if live_row is not None else None
    promotion = Promotion.model_validate(promotion_json) if promotion_json is not None else None
    names = {DEFAULT_TARGET, *(cast(str, row["name"]) for row in target_rows)}
    embeddings = {cast(str, row["name"]): row["embedding"] for row in target_rows}
    records = tuple(
        TargetRecord(
            name=name,
            embedding=EmbeddingIdentity.model_validate(embeddings[name])
            if embeddings.get(name) is not None
            else None,
        )
        for name in sorted(names)
    )
    return TargetCatalogue(live=live, previous=previous, targets=records, promotion=promotion)


async def claim_embedding(
    layout: PgTargetLayout,
    conn: "psycopg.AsyncConnection[dict[str, Any]]",
    home_schema: str,
    target: TargetName,
    identity: EmbeddingIdentity,
) -> EmbeddingIdentity:
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL(
                "INSERT INTO {} (name, embedding) VALUES (%(name)s, %(embedding)s) "
                "ON CONFLICT (name) DO UPDATE SET "
                "embedding = COALESCE({}.embedding, EXCLUDED.embedding) "
                "RETURNING embedding"
            ).format(
                home_table(home_schema, layout.targets_table),
                home_table(home_schema, layout.targets_table),
            ),
            {"name": target, "embedding": Jsonb(identity.model_dump(mode="json"))},
        )
        row = await cur.fetchone()
    if row is None:
        raise AssertionError("INSERT ... RETURNING must return exactly one row")
    return EmbeddingIdentity.model_validate(row["embedding"])


async def catalogue_names(
    layout: PgTargetLayout, cur: "psycopg.AsyncCursor[dict[str, Any]]", home_schema: str
) -> tuple[str, ...]:
    await cur.execute(
        sql.SQL("SELECT name FROM {}").format(home_table(home_schema, layout.targets_table))
    )
    rows = await cur.fetchall()
    return tuple(sorted({DEFAULT_TARGET, *(cast(str, row["name"]) for row in rows)}))


async def promote(
    layout: PgTargetLayout,
    conn: "psycopg.AsyncConnection[dict[str, Any]]",
    home_schema: str,
    promotion: Promotion,
) -> TargetCatalogue:
    """Promoting the target that is already live is a no-op: `previous` is never rewritten to
    the already-live target, so a converging re-run after a crash leaves the rollback an
    operator needs intact.
    """
    async with conn.transaction(), conn.cursor() as cur:
        if promotion.target != DEFAULT_TARGET:
            await cur.execute(
                sql.SQL("SELECT name FROM {} WHERE name = %s FOR SHARE").format(
                    home_table(home_schema, layout.targets_table)
                ),
                (promotion.target,),
            )
            if await cur.fetchone() is None:
                raise UnknownTargetError(
                    promotion.target,
                    valid_options=await catalogue_names(layout, cur, home_schema),
                )
        await cur.execute(
            sql.SQL("SELECT live FROM {}").format(home_table(home_schema, layout.live_target_table))
        )
        current = await cur.fetchone()
        old_live = TargetName(cast(str, current["live"])) if current else DEFAULT_TARGET
        if old_live == promotion.target:
            return await target_catalogue(layout, conn, home_schema)
        await cur.execute(
            sql.SQL(
                "INSERT INTO {} (singleton, live, previous, promotion) "
                "VALUES (true, %(live)s, %(previous)s, %(promotion)s) "
                "ON CONFLICT (singleton) DO UPDATE SET "
                "live = EXCLUDED.live, previous = EXCLUDED.previous, "
                "promotion = EXCLUDED.promotion"
            ).format(home_table(home_schema, layout.live_target_table)),
            {
                "live": promotion.target,
                "previous": old_live,
                "promotion": Jsonb(promotion.model_dump(mode="json")),
            },
        )
    return await target_catalogue(layout, conn, home_schema)


async def rollback(
    layout: PgTargetLayout, conn: "psycopg.AsyncConnection[dict[str, Any]]", home_schema: str
) -> TargetCatalogue:
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SELECT live, previous FROM {}").format(
                home_table(home_schema, layout.live_target_table)
            )
        )
        current = await cur.fetchone()
        live = TargetName(cast(str, current["live"])) if current else DEFAULT_TARGET
        previous = current["previous"] if current else None
        if previous is None:
            raise NoPreviousTargetError(live)
        await cur.execute(
            sql.SQL("UPDATE {} SET live = %(live)s, previous = %(previous)s").format(
                home_table(home_schema, layout.live_target_table)
            ),
            {"live": previous, "previous": live},
        )
    return await target_catalogue(layout, conn, home_schema)


async def drop_target(
    layout: PgTargetLayout,
    conn: "psycopg.AsyncConnection[dict[str, Any]]",
    home_schema: str,
    target: TargetName,
) -> None:
    catalogue = await target_catalogue(layout, conn, home_schema)
    known = {record.name for record in catalogue.targets}
    if target != DEFAULT_TARGET and target not in known:
        raise UnknownTargetError(target, valid_options=tuple(sorted(known)))
    if target == catalogue.live or target == catalogue.previous:
        raise TargetInUseError(target)
    locked = target == DEFAULT_TARGET
    if not locked:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired",
                (lock_key(layout, target),),
            )
            row = await cur.fetchone()
            locked = bool(row["acquired"]) if row is not None else False
        if not locked:
            raise TargetInUseError(target, reason="another connection is bound to it")
    try:
        async with conn.transaction(), conn.cursor() as cur:
            if target == DEFAULT_TARGET:
                for table in layout.target_tables:
                    await cur.execute(
                        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                            home_table(home_schema, table)
                        )
                    )
            else:
                await cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        target_schema(layout, target)
                    )
                )
            await cur.execute(
                sql.SQL("DELETE FROM {} WHERE name = %s").format(
                    home_table(home_schema, layout.targets_table)
                ),
                (target,),
            )
    finally:
        if target != DEFAULT_TARGET:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))", (lock_key(layout, target),)
                )
