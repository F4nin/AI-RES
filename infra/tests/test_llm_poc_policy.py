"""S16: optional gateway must not introduce a route from Runtime to the internet/admin/data."""
import copy
import re

import check_compose as cc
import pytest
import secrets_dev as sd

from tests.test_check_compose import good_model, good_service


def poc_model():
    model = good_model()
    model["networks"].update(llm_poc={"internal": True}, llm_upstream={"internal": True})
    model["services"].update({
        "bifrost-poc": good_service(
            networks={"llm_poc": None, "llm_upstream": None}, profiles=["llm-poc"],
            secrets=["bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth"],
        ),
        "llm-gateway": good_service(networks={"llm_upstream": None, "egress": None}, profiles=["llm-poc"], secrets=["llm_relay_auth"]),
    })
    return model


def test_isolated_poc_is_allowed_without_changing_the_existing_stack():
    assert cc.check_model(poc_model(), {}) == []
    assert cc.check_model(good_model(), {}) == []


@pytest.mark.parametrize(("service", "network"), [
    ("bifrost-poc", "egress"), ("bifrost-poc", "app"), ("bifrost-poc", "data"), ("bifrost-poc", "ingress"),
    ("llm-gateway", "app"), ("llm-gateway", "data"), ("llm-gateway", "admin"), ("llm-gateway", "llm_poc"),
    ("api", "llm_poc"), ("api", "llm_upstream"), ("worker-runtime", "llm_poc"),
])
def test_bypass_or_cross_boundary_network_membership_is_denied(service, network):
    model = poc_model()
    model["services"].setdefault(service, good_service(networks={"app": None}))
    model["services"][service]["networks"][network] = None
    assert cc.check_model(model, {})


@pytest.mark.parametrize("service", ["bifrost-poc", "llm-gateway"])
def test_poc_never_starts_by_default_or_exposes_host_ports(service):
    for mutation in ({"profiles": []}, {"profiles": ["bootstrap"]}, {"ports": [{"target": 8080, "published": "8080"}]}):
        model = poc_model()
        model["services"][service].update(mutation)
        assert cc.check_model(model, {})


def test_external_route_requires_both_gateway_components():
    model = poc_model()
    del model["services"]["bifrost-poc"]
    assert cc.check_model(model, {})


@pytest.mark.parametrize("service", ["api", "worker-runtime", "bifrost-poc", "llm-gateway"])
def test_provider_and_admin_credentials_never_reach_an_unrelated_service(service):
    model = poc_model()
    model["services"].setdefault(service, good_service(networks={"app": None}))
    model["services"][service]["secrets"] = ["deepseek_api_key", "api_db_password"]
    assert cc.check_model(model, {})


def test_gateway_cannot_use_an_open_undeclared_alternative_network():
    model = copy.deepcopy(poc_model())
    model["networks"]["llm_upstream"]["internal"] = False
    assert cc.check_model(model, {})


def test_poc_credentials_are_random_hex_and_never_provider_credentials():
    for name in ("bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth"):
        first, second = sd._generate(name), sd._generate(name)
        assert re.fullmatch(r"[0-9a-f]{64}", first)
        assert first != second
        assert name in sd.NAMES
    assert "deepseek_api_key" not in sd.NAMES  # provider keys are supplied by the owner; never fabricated by init
