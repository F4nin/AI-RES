"""Deterministic design snapshot of `ai_res_db` after `alembic upgrade head` (PERSIST-024, ADR-048).

pg_dump (same major as the server, run inside the container) gives schemas, ownership, tables, policies, ACLs and default privileges;
a catalog section adds what pg_dump omits (cluster-level role attributes, memberships, per-role settings, database ACL). Passwords,
OIDs, versions and random tokens are excluded so the text is reproducible. Foreign schemas (langgraph/temporal) are excluded.
"""
import re

from .conftest import Pg

_ROLE_SQL = """
SELECT format('ROLE %s %s %s', rolname,
       concat_ws(' ', CASE WHEN rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END, CASE WHEN rolinherit THEN 'INHERIT' ELSE 'NOINHERIT' END,
                 CASE WHEN rolsuper THEN 'SUPERUSER' ELSE 'NOSUPERUSER' END, CASE WHEN rolcreatedb THEN 'CREATEDB' ELSE 'NOCREATEDB' END,
                 CASE WHEN rolcreaterole THEN 'CREATEROLE' ELSE 'NOCREATEROLE' END, CASE WHEN rolreplication THEN 'REPLICATION' ELSE 'NOREPLICATION' END,
                 CASE WHEN rolbypassrls THEN 'BYPASSRLS' ELSE 'NOBYPASSRLS' END),
       coalesce((SELECT 'SET ' || string_agg(c, ', ' ORDER BY c)
                   FROM pg_db_role_setting s, unnest(s.setconfig) c WHERE s.setrole = r.oid AND s.setdatabase = 0), ''))
  FROM pg_roles r WHERE rolname LIKE 'ai\\_res\\_%' ORDER BY rolname
"""
_MEMBER_SQL = """
SELECT format('GRANT %s TO %s INHERIT=%s SET=%s', pg_get_userbyid(m.roleid), pg_get_userbyid(m.member), m.inherit_option, m.set_option)
  FROM pg_auth_members m WHERE pg_get_userbyid(m.roleid) LIKE 'ai\\_res\\_%' OR pg_get_userbyid(m.member) LIKE 'ai\\_res\\_%' ORDER BY 1
"""
_DBACL_SQL = """
SELECT format('DATABASE ACL %s', coalesce(array_to_string(ARRAY(SELECT x::text FROM unnest(datacl) x ORDER BY x::text), ','), '<default>'))
  FROM pg_database WHERE datname = current_database()
"""


def _normalize(dump: str) -> str:
    lines = [ln.rstrip() for ln in dump.splitlines() if not ln.startswith(("--", "\\restrict", "\\unrestrict"))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def build_snapshot(pg: Pg) -> str:
    code, out = pg.container.exec(["pg_dump", "-U", "postgres", "-d", "ai_res_db", "--schema-only", "--no-comments", "--no-tablespaces",
                                   "--exclude-schema=langgraph", "--exclude-schema=temporal"])
    assert code == 0, out.decode(errors="replace")[-800:]
    with pg.connect() as c:
        catalog = [r[0] for sql in (_ROLE_SQL, _MEMBER_SQL, _DBACL_SQL) for r in c.execute(sql.encode()).fetchall()]
    header = "-- AI RES design snapshot of ai_res_db at Alembic head (S04). Regenerate: make db-snapshot. Do not edit by hand.\n"
    return header + "\n-- CATALOG\n" + "\n".join(f"-- {line}" for line in catalog) + "\n\n-- SCHEMA\n" + _normalize(out.decode())
