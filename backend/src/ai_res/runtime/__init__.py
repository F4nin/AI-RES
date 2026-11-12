"""Manager and Worker Runtime processes (S11). DB-free by construction (import-linter): no database driver, no ORM, no domain modules. PostgreSQL
credentials are never supplied to these processes (Security v1.2, Spec §9); the domain is reached only through the internal Platform API."""
