"""seam ②：provider 预设表——预设填的是没被给的那几项，MUST NOT 覆盖已给出的那一项。

判的是 `layer_settings` 出来的那三项配对：provider 名字说 openai，端点三项就得是 openai 的预设。
今天这四个默认是两套不相关的东西（provider 默认 mock、端点默认 deepseek），所以
`--provider openai` 不带 `--base-url` 连的是 deepseek 端点。
"""

from __future__ import annotations

import argparse

from mini_harness.config.layering import layer_settings


def _layered(provider: str, config: dict[str, object] | None = None) -> object:
    """只给 provider，端点三项一律「没给」：判的就是预设本身。"""
    args = argparse.Namespace(provider=provider)
    return layer_settings(args, config or {})


def test_the_openai_preset_is_openai_not_deepseek() -> None:
    layered = _layered("openai")

    assert layered.base_url == "https://api.openai.com/v1"
    assert layered.model is None
    assert layered.api_key_env == "MINIHNS_API_KEY"


def test_the_deepseek_preset_is_the_deepseek_triple() -> None:
    layered = _layered("deepseek")

    assert layered.base_url == "https://api.deepseek.com"
    assert layered.model == "deepseek-chat"
    assert layered.api_key_env == "DEEPSEEK_API_KEY"


def test_the_mock_preset_has_no_endpoint() -> None:
    layered = _layered("mock")

    assert layered.base_url is None
    assert layered.model is None
    assert layered.api_key_env is None


def test_the_preset_never_overrides_a_flag_that_was_given() -> None:
    """CLI 给过的那一项预设一项都不覆盖：三项全给时生效的就是给进去的三项。"""
    args = argparse.Namespace(
        provider="openai",
        base_url="http://127.0.0.1:8300/v1",
        model="q",
        api_key_env="MINIHNS_TEST_PRESET_ENV",
    )

    layered = layer_settings(args, {})

    assert layered.base_url == "http://127.0.0.1:8300/v1"
    assert layered.model == "q"
    assert layered.api_key_env == "MINIHNS_TEST_PRESET_ENV"


def test_the_preset_never_overrides_a_model_the_config_file_gave() -> None:
    """配置文件给过 `model` 时预设同样不覆盖它，没给的那两项才落到预设。"""
    args = argparse.Namespace(provider="openai")

    layered = layer_settings(args, {"model": "config-model"})

    assert layered.model == "config-model"
    assert layered.base_url == "https://api.openai.com/v1"
    assert layered.api_key_env == "MINIHNS_API_KEY"


def test_a_config_file_provider_gets_its_own_preset() -> None:
    """provider 取自配置文件时预设同样生效：端点三项跟着这个名字走。"""
    args = argparse.Namespace()

    layered = layer_settings(args, {"provider": "deepseek"})

    assert layered.provider == "deepseek"
    assert layered.base_url == "https://api.deepseek.com"
    assert layered.model == "deepseek-chat"
    assert layered.api_key_env == "DEEPSEEK_API_KEY"
