"""Agent Skill 原生支持（Core Layer）。

遵循 Agent Skills 开放标准（https://agentskills.io/specification，
由 Anthropic 发起维护）实现：

    skill-name/
    ├── SKILL.md        # 必需：YAML frontmatter（name/description）+ Markdown 指令
    ├── scripts/        # 可选：可执行代码
    ├── references/     # 可选：参考文档
    └── assets/         # 可选：模板与静态资源

公开接口：Skill, SkillRegistry
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from thinkstack.errors import SkillError

# SKILL.md 中 YAML frontmatter 的分隔符
_FRONTMATTER_DELIM = "---"

# name 字段规范：1-64 字符，仅小写字母/数字/连字符，不能以连字符开头或结尾，
# 不能包含连续连字符（对应 agentskills.io 规范）
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_name(name: str) -> None:
    """按 Agent Skills 规范校验 skill name。"""
    if not name or len(name) > 64:
        raise SkillError(f"skill name 长度必须为 1-64 字符，当前 {len(name)} 字符")
    if not _NAME_RE.match(name):
        raise SkillError(
            f"skill name {name!r} 非法：仅允许小写字母/数字/连字符，"
            "不能以连字符开头或结尾，不能包含连续连字符"
        )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 SKILL.md：返回 (frontmatter 键值对, 正文 Markdown)。

    仅支持标准的 `key: value` 标量行与 `metadata:` 下的两级缩进键值对，
    不引入 YAML 依赖；frontmatter 缺失或非法时抛 SkillError。
    """
    if not text.startswith(_FRONTMATTER_DELIM):
        raise SkillError("SKILL.md 必须以 --- 开头的 YAML frontmatter 开始")
    lines = text.splitlines()
    if len(lines) < 2 or lines[1].strip() == _FRONTMATTER_DELIM:
        raise SkillError("SKILL.md frontmatter 为空")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            end = i
            break
    if end is None:
        raise SkillError("SKILL.md frontmatter 缺少结束分隔符 ---")

    front: dict[str, Any] = {}
    meta: dict[str, str] = {}
    in_meta = False
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_meta = False
            if ":" not in raw:
                raise SkillError(f"frontmatter 行无法解析：{raw!r}")
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                raise SkillError(f"frontmatter 行缺少键：{raw!r}")
            if key == "metadata":
                in_meta = True
                front[key] = meta
            else:
                front[key] = value
        elif indent >= 2 and in_meta:
            if ":" not in raw:
                continue
            k, _, v = raw.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
        else:
            raise SkillError(f"frontmatter 缩进无法解析：{raw!r}")

    body = "\n".join(lines[end + 1 :]).strip()
    return front, body


class Skill:
    """一个已加载的 Agent Skill（对应 skill 目录 + SKILL.md）。

    属性与 agentskills.io 规范的 frontmatter 字段一一对应；
    `content` 为 SKILL.md 正文指令，`path` 为 skill 根目录。
    """

    def __init__(
        self,
        name: str,
        description: str,
        content: str,
        path: str,
        *,
        license: Optional[str] = None,
        compatibility: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        allowed_tools: Optional[str] = None,
    ) -> None:
        _validate_name(name)
        if not description or len(description) > 1024:
            raise SkillError("skill description 长度必须为 1-1024 字符")
        self.name = name
        self.description = description
        self.content = content
        self.path = os.path.abspath(path)
        self.license = license
        self.compatibility = compatibility
        self.metadata: dict[str, str] = metadata or {}
        self.allowed_tools = allowed_tools

    # ------------------------------------------------------------------ 加载

    @classmethod
    def from_skill_dir(cls, path: str) -> "Skill":
        """从 skill 根目录加载：读取 SKILL.md 并解析 frontmatter。

        skill 的 name 必须与父目录名一致（agentskills.io 规范）。
        """
        root = os.path.abspath(path)
        skill_md = os.path.join(root, "SKILL.md")
        if not os.path.isfile(skill_md):
            raise SkillError(f"{root} 不是合法 skill 目录：缺少 SKILL.md")
        try:
            with open(skill_md, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise SkillError(f"读取 SKILL.md 失败：{exc}") from exc

        front, body = _parse_frontmatter(text)
        name = str(front.get("name", "")).strip()
        description = str(front.get("description", "")).strip()
        if not name or not description:
            raise SkillError("SKILL.md frontmatter 必须包含 name 与 description")
        _validate_name(name)

        dir_name = os.path.basename(root.rstrip(os.sep))
        if dir_name != name:
            raise SkillError(
                f"skill name {name!r} 与目录名 {dir_name!r} 不一致"
                "（规范要求二者一致）"
            )

        metadata = front.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise SkillError("frontmatter 的 metadata 必须是键值对映射")

        return cls(
            name=name,
            description=description,
            content=body,
            path=root,
            license=front.get("license") or None,
            compatibility=front.get("compatibility") or None,
            metadata=metadata,
            allowed_tools=front.get("allowed-tools") or None,
        )

    # ------------------------------------------------------------------ 资源

    def resource_path(self, rel_path: str) -> str:
        """返回 skill 目录下资源的绝对路径；越界或不存在的文件抛 SkillError。"""
        if not rel_path:
            raise SkillError("资源路径不能为空")
        norm = os.path.normpath(rel_path)
        if norm.startswith("..") or os.path.isabs(norm):
            raise SkillError(f"资源路径越界：{rel_path!r}")
        target = os.path.join(self.path, norm)
        if not os.path.isfile(target):
            raise SkillError(f"资源不存在：{rel_path!r}")
        return target

    def read_resource(self, rel_path: str) -> str:
        """读取 skill 资源文件内容（UTF-8）。"""
        with open(self.resource_path(rel_path), "r", encoding="utf-8") as fh:
            return fh.read()

    def resource_list(self) -> list[str]:
        """列出 skill 目录下 scripts/ references/ assets/ 中的资源（相对路径）。"""
        found: list[str] = []
        for sub in ("scripts", "references", "assets"):
            base = os.path.join(self.path, sub)
            if not os.path.isdir(base):
                continue
            for dirpath, _, files in os.walk(base):
                for fname in sorted(files):
                    rel = os.path.relpath(os.path.join(dirpath, fname), self.path)
                    found.append(rel.replace(os.sep, "/"))
        return found

    # ------------------------------------------------------------------ 输出

    def to_markdown(self) -> str:
        """把 skill 渲染为可注入 Agent 上下文的完整指令文本。"""
        header = [
            f"# Skill: {self.name}",
            "",
            f"> {self.description}",
        ]
        if self.compatibility:
            header.append(f"> 环境要求 / Compatibility: {self.compatibility}")
        if self.license:
            header.append(f"> 许可证 / License: {self.license}")
        header.append("")
        header.append(self.content or "(该 skill 无正文指令)")
        resources = self.resource_list()
        if resources:
            header.append("")
            header.append("## 资源 / Bundled resources")
            header.append("可通过相对路径引用（如 scripts/x.py）：")
            for rel in resources:
                header.append(f"- `{rel}`")
        return "\n".join(header)

    def summary(self) -> dict[str, str]:
        """渐进式披露：仅返回元数据摘要（name + description）。"""
        return {"name": self.name, "description": self.description}

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Skill name={self.name!r} path={self.path!r}>"


class SkillRegistry:
    """Skill 注册表：管理已加载的 Agent Skill 集合。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    # ------------------------------------------------------------------ 加载

    def load(self, path: str) -> Skill:
        """加载单个 skill 目录（含 SKILL.md）。名称重复时抛 SkillError。"""
        skill = Skill.from_skill_dir(path)
        return self.register(skill)

    def load_dir(self, dir_path: str) -> list[Skill]:
        """扫描目录，加载其中全部含 SKILL.md 的子目录（顺序不确定时按名称排序）。"""
        base = os.path.abspath(dir_path)
        if not os.path.isdir(base):
            raise SkillError(f"skill 目录不存在：{base}")
        loaded: list[Skill] = []
        for entry in sorted(os.listdir(base)):
            candidate = os.path.join(base, entry)
            if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "SKILL.md")):
                loaded.append(self.load(candidate))
        return loaded

    def register(self, skill: Skill) -> Skill:
        """注册一个 Skill 实例。"""
        if skill.name in self._skills:
            raise SkillError(f"skill {skill.name!r} 已加载，名称不可重复")
        self._skills[skill.name] = skill
        return skill

    # ------------------------------------------------------------------ 查询

    def get(self, name: str) -> Skill:
        """按名称获取 skill，不存在抛 SkillError。"""
        try:
            return self._skills[name]
        except KeyError:
            raise SkillError(f"skill {name!r} 未加载") from None

    def unload(self, name: str) -> None:
        """卸载指定 skill。"""
        self._skills.pop(name, None)

    def list_skills(self) -> list[Skill]:
        """返回全部已加载 skill。"""
        return list(self._skills.values())

    def summaries(self) -> list[dict[str, str]]:
        """返回全部 skill 的元数据摘要（name + description）。"""
        return [s.summary() for s in self._skills.values()]

    def context(self) -> str:
        """渐进式披露：返回全部 skill 的摘要文本，供 Agent 启动时注入。

        Agent 需要完整指令时再通过内置 `skill` 工具按名称获取。
        """
        if not self._skills:
            return ""
        lines = ["## Available Agent Skills", ""]
        for s in self._skills.values():
            lines.append(f"- `{s.name}`: {s.description}")
        return "\n".join(lines)

    def __contains__(self, name: str) -> bool:
        return name in self._skills
