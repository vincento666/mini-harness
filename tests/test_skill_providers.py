"""seam ②：技能 provider 与分层注册表（skill-providers）。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.skill_providers import FilesystemProvider, SkillRegistry
from mini_harness.skills import RANK_PRESET_LAYER, Skill, SkillDiscovery


class _Provider:
    """测试用 provider：清单由构造时给定，正文与清单分开，方便证明读正文走的是谁。"""

    def __init__(
        self,
        name: str,
        skills: tuple[Skill, ...],
        *,
        complete: bool = True,
        bodies: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self._skills = skills
        self._complete = complete
        self._bodies = bodies or {}

    def list(self) -> SkillDiscovery:
        return SkillDiscovery(self._skills, self._complete)

    def get(self, skill: Skill) -> str:
        return self._bodies.get(skill.name, f"{self.name} 的正文")


def _skill(tmp_path: Path, name: str, rank: int) -> Skill:
    return Skill(name=name, description="描述", rank=rank, path=tmp_path / f"{name}.md")


def _write_skill(root: Path, name: str, body: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: 描述\n---\n{body}\n", encoding="utf-8")
    return path


def test_the_filesystem_provider_lists_four_roots_and_reads_a_body(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    home = tmp_path / "home"
    _write_skill(workspace / ".minihns" / "skills", "tdd", "项目内的正文")

    provider = FilesystemProvider.global_roots(workspace, {"MINIHNS_HOME": str(home)})
    discovery = provider.list()

    assert [skill.name for skill in discovery.skills] == ["tdd"]
    assert discovery.complete
    assert provider.get(discovery.skills[0]).strip() == "项目内的正文"


def test_the_near_layer_wins_by_name_across_ranks(tmp_path: Path) -> None:
    global_layer = _Provider("global", (_skill(tmp_path, "tdd", 100),))
    near_layer = _Provider(
        "preset", (_skill(tmp_path, "tdd", 600),), bodies={"tdd": "preset 的正文"}
    )

    registry = SkillRegistry(global_layer).scoped(near_layer)
    snapshot = registry.snapshot()

    assert [skill.name for skill in snapshot.skills] == ["tdd"]
    # 胜出的必须是层里那份：全局那份 rank 更低也不作数。
    assert snapshot.skills[0].rank == 600
    assert registry.get("tdd") == "preset 的正文"


def test_the_near_layer_adds_skills_the_global_layer_does_not_have(tmp_path: Path) -> None:
    global_layer = _Provider("global", (_skill(tmp_path, "alpha", 100),))
    near_layer = _Provider("preset", (_skill(tmp_path, "beta", RANK_PRESET_LAYER),))

    snapshot = SkillRegistry(global_layer).scoped(near_layer).snapshot()

    assert [skill.name for skill in snapshot.skills] == ["alpha", "beta"]


def test_the_snapshot_is_sorted_by_name(tmp_path: Path) -> None:
    global_layer = _Provider(
        "global", (_skill(tmp_path, "zeta", 100), _skill(tmp_path, "alpha", 200))
    )

    assert [skill.name for skill in SkillRegistry(global_layer).snapshot().skills] == [
        "alpha",
        "zeta",
    ]


def test_incomplete_layers_make_the_snapshot_incomplete(tmp_path: Path) -> None:
    global_layer = _Provider("global", (), complete=True)
    near_layer = _Provider("preset", (), complete=False)

    assert not SkillRegistry(global_layer).scoped(near_layer).snapshot().complete
    assert SkillRegistry(_Provider("broken", (), complete=False)).snapshot().complete is False


def test_get_routes_to_the_provider_that_owns_the_skill(tmp_path: Path) -> None:
    global_layer = _Provider(
        "global", (_skill(tmp_path, "tdd", 100),), bodies={"tdd": "全局的正文"}
    )
    near_layer = _Provider("preset", (_skill(tmp_path, "build", 50),), bodies={"build": "层的"})
    registry = SkillRegistry(global_layer).scoped(near_layer)

    assert registry.get("tdd") == "全局的正文"
    assert registry.get("build") == "层的"


def test_get_returns_none_for_an_unknown_name(tmp_path: Path) -> None:
    registry = SkillRegistry(_Provider("global", (_skill(tmp_path, "tdd", 100),)))

    assert registry.get("nope") is None


def test_a_layer_directory_order_decides_inside_one_layer(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_skill(first, "tdd", "第一目录")
    _write_skill(second, "tdd", "第二目录")

    provider = FilesystemProvider.from_dirs("preset:reader", [first, second])

    assert provider.get(provider.list().skills[0]).strip() == "第一目录"


def test_a_missing_layer_directory_is_an_empty_complete_layer(tmp_path: Path) -> None:
    provider = FilesystemProvider.from_dirs("preset:reader", [tmp_path / "nope"])

    discovery = provider.list()

    assert discovery.skills == ()
    assert discovery.complete
