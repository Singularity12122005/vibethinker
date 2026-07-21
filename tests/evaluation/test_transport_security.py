from __future__ import annotations

import pytest

from vibethinker_experiments.evaluation.generation import GenerationRequest
from vibethinker_experiments.evaluation.transport import (
    EndpointPolicy,
    HttpsJsonTransport,
    NetworkDisabledTransport,
)


def test_default_transport_has_no_network():
    with pytest.raises(RuntimeError, match="network is disabled"):
        NetworkDisabledTransport().post_json({"candidate_response": "synthetic"})


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://judge.example.test/v1/chat",
        "https://not-allowed.example.test/v1/chat",
        "https://user:secret@judge.example.test/v1/chat",
        "https://judge.example.test:8443/v1/chat",
    ],
)
def test_endpoint_requires_https_allowlist_and_no_url_credentials(endpoint):
    policy = EndpointPolicy(
        allowed_hosts=frozenset({"judge.example.test"}),
        data_sending_confirmed=True,
    )
    with pytest.raises(ValueError):
        HttpsJsonTransport(endpoint, policy=policy, api_key_env="JUDGE_KEY")


def test_external_data_sending_requires_explicit_confirmation():
    policy = EndpointPolicy(
        allowed_hosts=frozenset({"judge.example.test"}),
        data_sending_confirmed=False,
    )
    with pytest.raises(PermissionError, match="explicit confirmation"):
        HttpsJsonTransport(
            "https://judge.example.test/v1/chat",
            policy=policy,
            api_key_env="JUDGE_KEY",
        )


def test_key_value_is_not_stored_in_repr_or_generation_contract(monkeypatch):
    monkeypatch.setenv("JUDGE_KEY", "highly-sensitive-value")
    transport = HttpsJsonTransport(
        "https://judge.example.test/v1/chat",
        policy=EndpointPolicy(
            allowed_hosts=frozenset({"judge.example.test"}),
            data_sending_confirmed=True,
        ),
        api_key_env="JUDGE_KEY",
    )
    assert "highly-sensitive-value" not in repr(transport)
    assert not any(
        "key" in field.casefold() or "secret" in field.casefold()
        for field in GenerationRequest.__dataclass_fields__
    )
