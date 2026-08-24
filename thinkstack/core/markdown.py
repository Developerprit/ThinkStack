"""Markdown 到 HTML 的轻量转换器（纯标准库，无第三方依赖）。

针对 LLM 输出多为 Markdown 的场景，提供开箱即用的渲染能力。
支持：标题、加粗/斜体/删除线、行内代码、围栏代码块、链接、图片、
无序/有序列表、引用、表格、分隔线、段落与换行。

公开接口：markdown_to_html
"""

from __future__ import annotations

import html
import re

_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)\s*$")
_HR_RE = re.compile(r"^\s*([-*_])\s*(?:\1\s*){2,}$")


def markdown_to_html(text: str) -> str:
    """把 Markdown 文本转换为 HTML 片段。

    参数：
        text: Markdown 源文本。

    返回：
        转换后的 HTML 字符串（不含 <html>/<body> 外壳）。
    """
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    # 先提取围栏代码块，避免其内部内容被当作 Markdown 处理
    prepared, fenced = _extract_fenced_blocks(lines)

    out: list[str] = []
    list_stack: list[str] = []  # 当前未闭合的列表标签 "ul"/"ol"
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def close_lists() -> None:
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    i = 0
    n = len(prepared)
    while i < n:
        line = prepared[i]
        stripped = line.strip()

        # 围栏代码块占位符
        if stripped in fenced:
            flush_paragraph()
            close_lists()
            out.append(fenced[stripped])
            i += 1
            continue

        # 空白行：结束段落与列表
        if not stripped:
            flush_paragraph()
            close_lists()
            i += 1
            continue

        # 分隔线
        if _HR_RE.match(stripped):
            flush_paragraph()
            close_lists()
            out.append("<hr />")
            i += 1
            continue

        # ATX 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_paragraph()
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # 引用块
        if stripped.startswith(">"):
            flush_paragraph()
            close_lists()
            quote_lines: list[str] = []
            while i < n and prepared[i].strip().startswith(">"):
                quote_lines.append(prepared[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{markdown_to_html(chr(10).join(quote_lines))}</blockquote>")
            continue

        # 无序列表
        m = re.match(r"^([-*+])\s+(.*)$", stripped)
        if m:
            flush_paragraph()
            if not list_stack or list_stack[-1] != "ul":
                out.append("<ul>")
                list_stack.append("ul")
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        # 有序列表
        m = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if m:
            flush_paragraph()
            if not list_stack or list_stack[-1] != "ol":
                out.append("<ol>")
                list_stack.append("ol")
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        # 表格：当前行含 |，且下一行是分隔行（含 -）
        if "|" in line and i + 1 < n and _is_table_separator(prepared[i + 1]):
            flush_paragraph()
            close_lists()
            header = _split_table_row(line)
            i += 2  # 跳过表头与分隔行，指向首行数据
            rows: list[list[str]] = []
            while i < n and "|" in prepared[i] and prepared[i].strip():
                rows.append(_split_table_row(prepared[i]))
                i += 1
            out.append(_render_table(header, rows))
            continue

        # 普通段落
        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    close_lists()
    return "\n".join(out).strip()


def _extract_fenced_blocks(lines: list[str]) -> tuple[list[str], dict[str, str]]:
    """提取围栏代码块，返回 (替换后的行列表, {占位符: 代码块 HTML})。"""
    prepared: list[str] = []
    fenced: dict[str, str] = {}
    counter = 0
    i = 0
    n = len(lines)
    while i < n:
        m = _FENCE_RE.match(lines[i])
        if m:
            fence = m.group(1)
            lang = m.group(2)
            buf: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过闭合围栏（若存在）
            placeholder = f"\x00FENCED{counter}\x00"
            lang_attr = f' class="language-{html.escape(lang)}"' if lang else ""
            fenced[placeholder] = (
                f"<pre><code{lang_attr}>{html.escape(chr(10).join(buf))}</code></pre>"
            )
            prepared.append(placeholder)
            counter += 1
        else:
            prepared.append(lines[i])
            i += 1
    return prepared, fenced


def _is_table_separator(line: str) -> bool:
    """判断是否为 Markdown 表格的分隔行（如 |---|:---:|---|）。"""
    s = line.strip().strip("|")
    if "-" not in s:
        return False
    cells = s.split("|")
    return all(re.fullmatch(r":?-{1,}:?", c.strip()) for c in cells if c.strip() != "")


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_table(header: list[str], rows: list[list[str]]) -> str:
    parts = ["<table>", "<thead><tr>"]
    parts += [f"<th>{_inline(c)}</th>" for c in header]
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        parts += [f"<td>{_inline(c)}</td>" for c in row]
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _inline(text: str) -> str:
    """处理行内 Markdown：行内代码、图片、链接、加粗、斜体、删除线，并转义 HTML。"""
    code_spans: list[str] = []

    def _protect_code(m: re.Match) -> str:
        code_spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00CODE{len(code_spans) - 1}\x00"

    # 先保护行内代码，其内容会被转义并原样还原
    text = re.sub(r"`([^`]+)`", _protect_code, text)

    # 转义剩余文本（& < > 等），此后插入的标签不再被转义
    text = html.escape(text, quote=False)

    # 图片 ![alt](url)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}" />',
        text,
    )
    # 链接 [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    # 加粗
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    # 斜体（避免与加粗冲突）
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", text)
    # 删除线
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    # 还原行内代码
    text = re.sub(r"\x00CODE(\d+)\x00", lambda m: code_spans[int(m.group(1))], text)
    return text
