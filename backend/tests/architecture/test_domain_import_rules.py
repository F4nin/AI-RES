"""Exercise the actual ARCH-01 contracts against isolated synthetic packages."""
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
LINT = str(Path(sys.executable).parent / "lint-imports")
LAYERS = "Domain module layers (ARCH-01)"
PEERS = "Peer domain modules are independent (ARCH-01)"


def domain_contracts():
    contracts = tomllib.loads((BACKEND / "pyproject.toml").read_text())["tool"]["importlinter"]["contracts"]
    selected = [c for c in contracts if c["name"] in {LAYERS, PEERS}]
    assert len(selected) == 2, "Both ARCH-01 contracts must remain enabled"
    return {c["name"]: c for c in selected}


def test_all_domain_peers_have_independence_protection():
    contracts = domain_contracts()
    top_layer = contracts[LAYERS]["layers"][0]
    assert set(contracts[PEERS]["modules"]) == {f"ai_res.modules.{name}" for name in top_layer.split(":")}


@pytest.fixture
def domain_package(tmp_path):
    contracts = domain_contracts()
    modules = {name for layer in contracts[LAYERS]["layers"] for name in layer.split(":")}
    for name in ["ai_res", "ai_res.modules", *(f"ai_res.modules.{name}" for name in sorted(modules))]:
        package = tmp_path.joinpath(*name.split("."))
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("")
    # Reuse production options verbatim: a synthetic lookalike contract would not
    # detect a regression in pyproject.toml. Only unrelated contracts are omitted.
    config = '[tool.importlinter]\nroot_package = "ai_res"\n'
    for contract in contracts.values():
        config += "\n[[tool.importlinter.contracts]]\n"
        config += "\n".join(f"{key} = {json.dumps(value)}" for key, value in contract.items()) + "\n"
    (tmp_path / "pyproject.toml").write_text(config)
    return tmp_path


def check_imports(root, imports):
    for importer, imported in imports:
        path = root.joinpath(*importer.split(".")).with_suffix(".py")
        path.write_text(f"import {imported}\n")
    return subprocess.run(
        [LINT, "--no-cache"], cwd=root, capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_downward_and_shared_layer_imports_are_allowed(domain_package):
    result = check_imports(domain_package, [
        ("ai_res.modules.sources.service", "ai_res.modules.operations.service"),
        ("ai_res.modules.operations.service", "ai_res.modules.events.service"),
        ("ai_res.modules.events.service", "ai_res.modules.audit"),
        ("ai_res.modules.iam.service", "ai_res.modules.idempotency"),
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 kept, 0 broken" in result.stdout


@pytest.mark.parametrize(("lower", "higher"), [
    ("events", "operations"), ("audit", "requirements"), ("iam", "sources"),
])
def test_lower_layers_cannot_import_higher_layers(domain_package, lower, higher):
    result = check_imports(domain_package, [(f"ai_res.modules.{lower}.service", f"ai_res.modules.{higher}")])
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{LAYERS} BROKEN" in result.stdout
    assert "1 kept, 1 broken" in result.stdout


@pytest.mark.parametrize(("source", "target"), [("projects", "epics"), ("epics", "projects")])
def test_peer_imports_are_forbidden_in_both_directions(domain_package, source, target):
    result = check_imports(domain_package, [(f"ai_res.modules.{source}.service", f"ai_res.modules.{target}")])
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{PEERS} BROKEN" in result.stdout
    assert "1 kept, 1 broken" in result.stdout


@pytest.mark.parametrize(("source", "target", "broken"), [
    ("events", "sources", LAYERS), ("sources", "requirements", PEERS),
])
def test_indirect_imports_cannot_bypass_contracts(domain_package, source, target, broken):
    result = check_imports(domain_package, [
        (f"ai_res.modules.{source}.service", "ai_res.bridge"),
        ("ai_res.bridge", f"ai_res.modules.{target}"),
    ])
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{broken} BROKEN" in result.stdout
    assert "1 kept, 1 broken" in result.stdout


def test_new_module_requires_explicit_layer_classification(domain_package):
    package = domain_package / "ai_res" / "modules" / "unclassified"
    package.mkdir()
    (package / "__init__.py").write_text("")
    result = check_imports(domain_package, [])
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{LAYERS} BROKEN" in result.stdout
    assert "ai_res.modules.unclassified" in result.stdout
    assert "1 kept, 1 broken" in result.stdout
