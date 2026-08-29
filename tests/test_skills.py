"""test_skills.py —— 覆盖 Agent Skill 原生支持（agentskills.io 标准）。

包括：SKILL.md frontmatter 解析、name 校验、目录扫描、skill 工具、
上下文注入与 REST 端点。
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from thinkstack import (
    Skill,
    SkillError,
    SkillRegistry,
    ThinkStack,
    ThinkStackServer,
)


def _write_skill(root: str, name: str, description: str, body: str = "step 1\ndone") -> str:
    """在 root/name/ 下写入 SKILL.md，返回 skill 目录路径。"""
    skill_dir = os.path.join(root, name)
    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(skill_dir, "references"), exist_ok=True)
    md = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "license: Apache-2.0\n"
        "metadata:\n"
        "  author: kscm\n"
        "  version: \"1.0\"\n"
        "---\n"
        f"{body}\n"
    )
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(skill_dir, "scripts", "run.py"), "w", encoding="utf-8") as fh:
        fh.write("print('hello')\n")
    return skill_dir


# ---------------------------------------------------------------- 解析与校验

def test_parse_valid_skill(tmp_path):
    skill_dir = _write_skill(str(tmp_path), "hello-skill", "Greet the user. Use for greetings.")
    skill = Skill.from_skill_dir(skill_dir)
    assert skill.name == "hello-skill"
    assert skill.description == "Greet the user. Use for greetings."
    assert skill.license == "Apache-2.0"
    assert skill.metadata == {"author": "kscm", "version": "1.0"}
    assert "step 1" in skill.content
    assert "scripts/run.py" in skill.resource_list()


def test_name_must_match_directory(tmp_path):
    skill_dir = _write_skill(str(tmp_path), "hello-skill", "desc")
    # 重命名目录使其与 name 不一致
    wrong_dir = os.path.join(str(tmp_path), "other-name")
    os.rename(skill_dir, wrong_dir)
    with pytest.raises(SkillError, match="不一致"):
        Skill.from_skill_dir(wrong_dir)


def test_invalid_name_rejected(tmp_path):
    skill_dir = _write_skill(str(tmp_path), "bad-name", "desc")
    with open(os.path.join(skill_dir, "SKILL.md"), "r", encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("name: bad-name", "name: Bad-Name")
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with pytest.raises(SkillError, match="非法"):
        Skill.from_skill_dir(skill_dir)


def test_missing_description_rejected(tmp_path):
    skill_dir = _write_skill(str(tmp_path), "no-desc", "desc")
    with open(os.path.join(skill_dir, "SKILL.md"), "r", encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("description: desc\n", "")
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with pytest.raises(SkillError, match="description"):
        Skill.from_skill_dir(skill_dir)


def test_duplicate_name_rejected(tmp_path):
    d1 = _write_skill(str(tmp_path), "dup-skill", "one")
    reg = SkillRegistry()
    reg.load(d1)
    d2 = _write_skill(str(tmp_path), "dup-skill-2", "two")
    # 直接构造同名 skill 注册应报错
    skill2 = Skill.from_skill_dir(d2)
    skill2.name = "dup-skill"
    with pytest.raises(SkillError, match="已加载"):
        reg.register(skill2)


# ---------------------------------------------------------------- 目录扫描与工具

def test_load_dir_and_skill_tool(tmp_path):
    _write_skill(str(tmp_path), "alpha-skill", "Alpha skill.")
    _write_skill(str(tmp_path), "beta-skill", "Beta skill.")
    stack = ThinkStack()
    loaded = stack.load_skill_dir(str(tmp_path))
    assert len(loaded) == 2
    assert {s.name for s in loaded} == {"alpha-skill", "beta-skill"}

    # 内置 skill 工具：按名称获取完整指令
    result = stack.call_tool("skill", skill="alpha-skill")
    assert result.success
    assert "# Skill: alpha-skill" in result.data
    assert "step 1" in result.data

    # 未加载的 skill 报错
    missing = stack.call_tool("skill", skill="nope")
    assert not missing.success


def test_skill_context_injected_into_agent_loop(tmp_path):
    _write_skill(str(tmp_path), "guide-skill", "Guides the agent.")
    stack = ThinkStack()
    stack.load_skill_dir(str(tmp_path))
    stack.start()

    captured = {}

    class CtxAgent:
        name = "ctx-probe"

        def think(self, context):
            captured["skills"] = context.get("skills", "")
            return "ok"

        def act(self, thought):
            return thought

        def observe(self, action):
            return {"result": action}

        def should_stop(self, observation):
            return True

    stack.run_agent(CtxAgent(), "hi", max_iterations=1)
    assert "guide-skill" in captured["skills"]
    assert "Guides the agent." in captured["skills"]


# ---------------------------------------------------------------- REST 端点

def test_rest_skills_endpoints(tmp_path):
    _write_skill(str(tmp_path), "rest-skill", "REST skill.")
    stack = ThinkStack()
    stack.start()
    server = ThinkStackServer(stack, host="127.0.0.1", port=0)
    server.start(block=False)
    port = server._httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        # 空列表
        body = json.loads(urllib.request.urlopen(f"{base}/api/skills").read().decode())
        assert body["skills"] == []

        # 加载
        req = urllib.request.Request(
            f"{base}/api/skills/load",
            data=json.dumps({"path": os.path.join(str(tmp_path), "rest-skill")}).encode(),
            headers={"Content-Type": "application/json"},
        )
        loaded = json.loads(urllib.request.urlopen(req).read().decode())
        assert loaded["ok"] is True
        assert loaded["name"] == "rest-skill"

        # 列表
        body = json.loads(urllib.request.urlopen(f"{base}/api/skills").read().decode())
        assert [s["name"] for s in body["skills"]] == ["rest-skill"]

        # 卸载
        req = urllib.request.Request(
            f"{base}/api/skills/unload",
            data=json.dumps({"name": "rest-skill"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        unloaded = json.loads(urllib.request.urlopen(req).read().decode())
        assert unloaded["ok"] is True
    finally:
        server.shutdown()
        stack.shutdown()
