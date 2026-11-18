# ADR137 — отдельный защищённый candidate Bifrost

Это local/test образ, не замена official image/основного Compose, не Bifrost/profile approval и не live activation. [ADR137](../../../docs/implementation/decisions/ADR-137-candidate-configuration-integrity.md) определяет scope.

`build.py` использует неизменённый [SDK builder](../bifrost_patch/README.md) и verified sparse source, накладывает прежний fingerprint patch, затем разрешённые3transport paths из `integrity.patch`. Base locks/source/license/toolchain/runtime pins прежние. Manifest связывает новый patch/tool/launcher/template/Dockerfile с отдельным immutable image, новым provenance и baked launcher. Official/main tags не перезаписываются.

Из корня проекта:

```sh
backend/.venv/bin/python -B infra/llm_poc/bifrost_integrity/build.py
```

Опциональный `--snapshot /absolute/path/verified-sparse.tar` использует checksum-verified cache. Без него builder самостоятельно получает fixed public source по прежнему bounded workflow. Build получает только public vendor source/patches/tooling, не backend/секреты. Dependencies восстанавливаются по existing Go locks. Образ публиковать этим workflow нельзя.

Launcher требует пустой `/app/data` tmpfs, не удаляет старое состояние, очищает inherited env, штатно рендерит config и выполняет fixed binary. Bootstrap требует exact compiled template/catalogues/три mounted64hex, config0600 и enabled SQLite. Внешний HTTP guard разрешает только exact original `GET /health` и `POST /v1/chat/completions`; admin/UI/alternative routes запрещены даже с admin credentials.

Перед каждым разрешённым запросом guard проверяет input/rendered/marker bytes, live config и полный **логический** SQLite snapshot со schema/storage classes/visible columns/row multiplicity. Readonly transaction учитывает WAL; bookkeeping exceptions отсутствуют. Ошибка или наблюдаемый drift защёлкивают503 до нового процесса. Это не physical DB-byte attestation и не обнаружение любых промежуточных необнаруженных изменений.

Marker `candidate-integrity.json` создаётся после успешной инициализации: version/bootNonce/configSha256, mode0600, без newline/credentials. Host descriptor0.2 требует exact reviewed namespace hash; прежний0.1 отказывает. Observer читает фактический mount namespace под `env -i`, проверяет guarded health и bracketed Docker StartedAt/Pid/RestartCount/image/config. Не собирать hashes по одному host path и не считать marker approval. Default CLI/standalone listener остаются отключёнными для dispatch.

Native tests:

```sh
backend/.venv/bin/python -B -m pytest -q backend/tests/integration/test_bifrost_candidate_integrity.py
```

Только собственные containers/internal network/tmpfs и синтетический upstream. Test-only Go SQLite fault injector собирается отдельно по тем же locks и временно помещается в test `/tmp` с `exec`; **в candidate image, product Compose или real descriptor его нет**. Существующие SDK/official/mutable audit fixtures сохраняются и проверяются отдельно. Ключи/real accounts/tariffs/approvals не создаются, расходы к модели отсутствуют.

Перед настоящим допуском остаются final regression/pre-pr/LinuxCI/supply-chain gates, точный безопасный key setup, реальные provider observations и отдельные human Bifrost/profile approvals. Runtime/Manager/Worker не получают Docker socket или полномочия этого trusted development host.
