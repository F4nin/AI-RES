"""Temporal orchestration (S11): compact contracts, the deterministic Operation workflow skeleton, Activities and the process composition.

This package never imports the database layer, the policy engine or the domain modules (import-linter): Manager and Worker Runtime hold no DB
credentials and change the domain ONLY through the narrow Platform API port (`platform_port.OperationPlatform`, Contracts v1.10 §7.2).
"""
