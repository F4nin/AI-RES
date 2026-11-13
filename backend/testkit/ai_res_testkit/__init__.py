"""TEST-ONLY helpers (ADR-022, ADR-110).

This package lives outside `src/`: the wheel (`packages = ["src/ai_res"]`) and the backend image (`COPY src`) never contain it.
Importing it under an explicit non-test profile (`AI_RES_ENVIRONMENT` = prod or local) is an error: a second barrier behind Settings validation and the factory.
"""
import os

if os.environ.get("AI_RES_ENVIRONMENT", "test") != "test":
    raise ImportError("ai_res_testkit is test-only and cannot be imported when AI_RES_ENVIRONMENT is not 'test' (ADR-022)")
