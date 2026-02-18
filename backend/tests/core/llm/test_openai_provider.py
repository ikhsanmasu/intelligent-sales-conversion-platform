from app.core.llm.providers.openai import OpenAIProvider
from app.core.llm.schemas import GenerateConfig


def test_build_params_omits_none_optionals():
    provider = OpenAIProvider(api_key="test", model="gpt-5.2")

    params = provider._build_params(
        messages=[{"role": "user", "content": "hello"}],
        config=GenerateConfig(max_tokens=None, stop=None),
    )

    assert params["model"] == "gpt-5.2"
    assert "max_tokens" not in params
    assert "stop" not in params


def test_build_params_includes_optional_values_when_provided():
    provider = OpenAIProvider(api_key="test", model="gpt-5.2")

    params = provider._build_params(
        messages=[{"role": "user", "content": "hello"}],
        config=GenerateConfig(max_tokens=128, stop=["DONE"]),
    )

    assert params["max_tokens"] == 128
    assert params["stop"] == ["DONE"]
