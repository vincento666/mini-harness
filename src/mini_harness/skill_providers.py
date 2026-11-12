"""技能 provider 与分层注册表（skill-providers）。

DSH 的形状：provider 注册进 host 层或某个 scope 层，读时合并 scope 链，近层同名直接胜出。
mini 只做窄接口（list/get），唯一实现是 filesystem；没有生命周期、没有热更新（ADR-0040）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from mini_harness.skills import (
    Skill,
    SkillDiscovery,
    discover_skill_layer,
    discover_skills,
    read_skill_body,
)


class SkillProvider(Protocol):
    """一个技能来源：列出候选（带完整性）与读正文。"""

    name: str

    def list(self) -> SkillDiscovery: ...

    def get(self, skill: Skill) -> str: ...


class FilesystemProvider:
    """本地目录 provider：包装一个扫描闭包。"""

    def __init__(self, name: str, load: Callable[[], SkillDiscovery]) -> None:
        self.name = name
        self._load = load

    @classmethod
    def global_roots(cls, workspace: Path, environ: Mapping[str, str]) -> FilesystemProvider:
        return cls("filesystem", lambda: discover_skills(workspace, environ))

    @classmethod
    def from_dirs(cls, name: str, directories: Sequence[Path]) -> FilesystemProvider:
        return cls(name, lambda: discover_skill_layer(directories))

    def list(self) -> SkillDiscovery:
        return self._load()

    def get(self, skill: Skill) -> str:
        return read_skill_body(skill)


class SkillRegistry:
    """分层注册表：近层在前，全局层在后；同名只由最近的层回答。"""

    def __init__(self, global_provider: SkillProvider) -> None:
        self._global = global_provider
        self._scopes: tuple[SkillProvider, ...] = ()

    def scoped(self, provider: SkillProvider) -> SkillRegistry:
        """挂一层更近的 provider；链上仍只有一份全局层。"""
        registry = SkillRegistry(self._global)
        registry._scopes = (provider, *self._scopes)
        return registry

    def _providers(self) -> tuple[SkillProvider, ...]:
        return (*self._scopes, self._global)

    def snapshot(self) -> SkillDiscovery:
        """近层先占名字，全局层只补没被覆盖的；按名字排序。"""
        by_name: dict[str, Skill] = {}
        complete = True
        for provider in self._providers():
            view = provider.list()
            complete = complete and view.complete
            for skill in view.skills:
                by_name.setdefault(skill.name, skill)
        return SkillDiscovery(
            skills=tuple(sorted(by_name.values(), key=lambda skill: skill.name)),
            complete=complete,
        )

    def get(self, name: str) -> str | None:
        """正文由拥有这个名字的那一层提供——不是就地读文件。"""
        for provider in self._providers():
            for skill in provider.list().skills:
                if skill.name == name:
                    return provider.get(skill)
        return None


def visible_skills(registry: SkillRegistry | None, fallback: Sequence[Skill]) -> tuple[Skill, ...]:
    """命令面与目录共用的视图：有注册表读快照，没有（裸 env / 旧测试）回落到装配快照。"""
    return registry.snapshot().skills if registry is not None else tuple(fallback)
