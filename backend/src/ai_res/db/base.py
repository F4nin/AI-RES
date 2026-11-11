"""Metadata registry, naming convention and the schema allowlist (ADR-014, Blueprint §4.2).

Temporal/LangGraph schemas are NOT in the allowlist: Alembic must neither see nor touch them (DBM-002, ADR-036).
"""
from sqlalchemy import MetaData

# Explicit, stable names for every constraint/index (Strategy §4.2): autogenerate output is reviewed against this convention.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ADR-014. `platform` hosts the Alembic version table and is created by env.py before the first revision.
DOMAIN_SCHEMAS: tuple[str, ...] = (
    "iam", "organization", "project", "work", "requirements", "sources", "knowledge", "decisions", "artifacts",
    "traceability", "governance", "agents", "context", "integrations", "audit", "platform", "operations", "execution",
)
VERSION_TABLE_SCHEMA = "platform"
OWNER_ROLE = "ai_res_owner"

metadata = MetaData(naming_convention=NAMING_CONVENTION)
