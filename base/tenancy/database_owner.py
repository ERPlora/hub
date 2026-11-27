"""A database of the cluster, created for its owner or handed back to it."""

import psycopg
from psycopg import sql


def _ensure_database(
    conn: psycopg.Connection, database: str, owner: str
) -> tuple[str, str]:
    row = conn.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", [database]
    ).fetchone()
    if row is None:
        try:
            conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(owner)
                )
            )
        except psycopg.errors.DuplicateDatabase:
            return _ensure_database(
                conn, database, owner
            )  # created meanwhile: converge
        return "created", f"owner {owner}"
    if row[0] != owner:
        conn.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(database), sql.Identifier(owner)
            )
        )
        return "updated", f"owner {owner}, was {row[0]}"
    return "exists", f"owner {owner}"
