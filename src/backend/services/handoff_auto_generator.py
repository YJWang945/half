import json
import logging
import re

from sqlalchemy.orm import Session

from models import Project, Task

logger = logging.getLogger("half.handoff_auto")

_MAX_REPORT_BYTES = 50_000

# ——— 边类型推断 ———

_EDGE_TYPE_PATTERNS: list[tuple[list[str], list[str], str]] = [
    (["DEV", "开发"], ["TEST", "测试"], "dev-to-test"),
    (["DEV", "开发"], ["REVIEW", "评审", "审查"], "dev-to-review"),
    (["TEST", "测试"], ["DEV", "开发", "REVISE", "修改", "修复", "FIX"], "test-to-revise"),
    (["REVIEW", "评审"], ["DEV", "开发", "REVISE", "修改"], "review-to-revise"),
]


def infer_edge_type(from_task: Task, to_task: Task) -> str:
    from_text = f"{from_task.task_code or ''} {from_task.task_name or ''}".upper()
    to_text = f"{to_task.task_code or ''} {to_task.task_name or ''}".upper()
    for from_pats, to_pats, edge_type in _EDGE_TYPE_PATTERNS:
        if any(p.upper() in from_text for p in from_pats) and any(
            p.upper() in to_text for p in to_pats
        ):
            return edge_type
    return "general"


# ——— Markdown section 提取 ———

_SECTION_KEYWORD_MAP: dict[str, list[str]] = {
    "core_changes": ["核心变更", "变更", "修改", "改动", "changes"],
    "test_focus": ["测试重点", "验证", "测试", "test"],
    "risks": ["风险", "risk", "未决", "caveat", "限制"],
    "change_scope": ["修改范围", "范围", "scope"],
    "review_points": ["评审要点", "审查", "review"],
    "notes": ["注意", "说明", "note", "备注"],
    "test_conclusion": ["测试结论", "结论", "conclusion"],
    "issues_found": ["发现", "问题", "issue", "bug"],
    "suggestions": ["建议", "修改建议", "suggestion", "改进"],
    "upstream_conclusion": ["上游结论", "结论", "summary"],
    "downstream_concerns": ["下游需关注", "下游", "关注"],
    "caveats": ["caveat", "注意事项", "⚠"],
}


def _extract_sections_from_markdown(md_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    parts = re.split(r"\n(?=## [^#])", md_text)
    for part in parts:
        match = re.match(r"^## (.+)$", part, re.MULTILINE)
        if not match:
            continue
        heading = match.group(1).strip()
        body = part[match.end() :].strip()
        heading_lower = heading.lower()
        for canonical, keywords in _SECTION_KEYWORD_MAP.items():
            if any(kw.lower() in heading_lower for kw in keywords):
                if canonical in sections:
                    sections[canonical] += "\n\n" + body
                else:
                    sections[canonical] = body
                break
    return sections


# ——— 边类型 → details section 渲染规格 ———

_RENDER_SPECS: dict[str, list[tuple[str, str]]] = {
    "dev-to-test": [
        ("## 核心变更", "core_changes"),
        ("## 测试重点", "test_focus"),
        ("## 风险提示", "risks"),
        ("## 相关工件", "artifacts_list"),
    ],
    "dev-to-review": [
        ("## 修改范围", "change_scope"),
        ("## 评审要点", "review_points"),
        ("## 注意事项", "notes"),
        ("## 相关工件", "artifacts_list"),
    ],
    "test-to-revise": [
        ("## 测试结论", "test_conclusion"),
        ("## 发现问题", "issues_found"),
        ("## 修改建议", "suggestions"),
        ("## 相关工件", "artifacts_list"),
    ],
    "review-to-revise": [
        ("## 审查结论", "review_points"),
        ("## 发现问题", "issues_found"),
        ("## 修改建议", "suggestions"),
        ("## 相关工件", "artifacts_list"),
    ],
    "general": [
        ("## 上游结论", "upstream_conclusion"),
        ("## 下游需关注", "downstream_concerns"),
        ("## 风险 / 未决问题", "risks"),
        ("## 相关工件", "artifacts_list"),
    ],
}

_EDGE_TYPE_SUMMARY_PREFIX: dict[str, str] = {
    "dev-to-test": "已完成代码修改，请按以下内容进行测试验证。",
    "dev-to-review": "代码实现已完成，请围绕修改范围和边界条件进行专项审查。",
    "test-to-revise": "测试已完成，请根据发现的问题进行修改。",
    "review-to-revise": "代码审查已完成，请根据审查意见进行修改。",
    "general": "上游任务已完成，请根据以下交接内容继续执行。",
}


# ——— 第 1 阶段：构建上下文包 ———


def build_source_context(
    db: Session, project: Project, from_task: Task
) -> dict:
    from services import git_service

    collab_dir = (project.collaboration_dir or "").strip("/")
    task_dir = f"{collab_dir}/{from_task.task_code}"

    result_json = None
    report_files: dict[str, str] = {}
    warnings: list[str] = []

    # 读取 result.json
    result_json = git_service.read_json(
        project.id,
        f"{task_dir}/result.json",
        project.git_repo_url,
        prefer_remote=True,
    )
    if result_json is None:
        warnings.append("上游任务未找到 result.json，部分上下文缺失")
    elif not isinstance(result_json, dict):
        warnings.append("上游 result.json 格式异常")
        result_json = None
    else:
        if "summary" not in result_json or not str(result_json.get("summary", "")).strip():
            warnings.append("上游 result.json 缺少 summary 字段")

        # 读取 report 类型工件
        artifacts = result_json.get("artifacts", [])
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                path = artifact.get("path", "")
                atype = str(artifact.get("type", "")).lower()
                if atype == "report" or str(path).lower().endswith(".md"):
                    content = _safe_read_file(
                        git_service, project, path
                    )
                    if content:
                        report_files[path] = content

    # 如果 result.json 的 artifacts 没有报告，扫描任务目录下的 .md 文件
    if not report_files:
        try:
            entries = git_service.list_dir(
                project.id,
                task_dir,
                project.git_repo_url,
                prefer_remote=True,
            )
            for entry in entries or []:
                if entry.lower().endswith(".md"):
                    full_path = f"{task_dir}/{entry}"
                    if full_path not in report_files:
                        content = _safe_read_file(
                            git_service, project, full_path
                        )
                        if content:
                            report_files[full_path] = content
        except Exception:
            pass

    return {
        "result_json": result_json,
        "report_files": report_files,
        "collection_warnings": warnings,
    }


def _safe_read_file(git_service, project: Project, relative_path: str) -> str | None:
    try:
        content = git_service.read_file(
            project.id,
            relative_path,
            project.git_repo_url,
            prefer_remote=True,
        )
        if content and len(content) > _MAX_REPORT_BYTES:
            content = content[:_MAX_REPORT_BYTES]
        return content
    except Exception:
        return None


# ——— 第 2 阶段：事实抽取 ———


def extract_facts(
    source_context: dict, from_task: Task, to_task: Task
) -> dict:
    edge_type = infer_edge_type(from_task, to_task)
    warnings: list[str] = []

    # 从 result.json 提取 summary
    summary = ""
    result_json = source_context.get("result_json")
    if isinstance(result_json, dict):
        summary = str(result_json.get("summary", "")).strip()

    # 构建工件列表
    artifacts_list = _build_artifacts_markdown(result_json)

    # 提取所有报告中的 section
    merged_sections: dict[str, str] = {}
    report_files: dict[str, str] = source_context.get("report_files", {})
    for _filename, content in report_files.items():
        sections = _extract_sections_from_markdown(content)
        for canonical, body in sections.items():
            if canonical in merged_sections:
                merged_sections[canonical] += "\n\n---\n\n" + body
            else:
                merged_sections[canonical] = body

    facts: dict[str, str] = {**merged_sections}
    facts["summary"] = summary
    facts["artifacts_list"] = artifacts_list

    # 边类型特定的 fallback 填充
    if edge_type == "dev-to-test":
        if not facts.get("core_changes"):
            facts["core_changes"] = _fallback_from_description(from_task)
        if not facts.get("test_focus"):
            facts["test_focus"] = _downstream_hint(to_task)
    elif edge_type == "dev-to-review":
        if not facts.get("change_scope"):
            facts["change_scope"] = _fallback_from_description(from_task)
        if not facts.get("review_points"):
            facts["review_points"] = _downstream_hint(to_task)
    elif edge_type in ("test-to-revise", "review-to-revise"):
        if not facts.get("test_conclusion") and not facts.get("review_points"):
            facts["upstream_conclusion"] = _fallback_from_description(from_task)
        if not facts.get("suggestions"):
            facts["suggestions"] = _downstream_hint(to_task)
    elif edge_type == "general":
        if not facts.get("upstream_conclusion"):
            facts["upstream_conclusion"] = _fallback_from_description(from_task)
        if not facts.get("downstream_concerns"):
            facts["downstream_concerns"] = _downstream_hint(to_task)

    # 将 risks 和 caveats 合并
    if facts.get("caveats"):
        risks = facts.get("risks", "")
        if risks:
            risks += "\n\n"
        risks += facts["caveats"]
        facts["risks"] = risks

    return {
        "edge_type": edge_type,
        "summary": summary,
        "facts": facts,
        "extraction_warnings": warnings,
    }


def _fallback_from_description(task: Task) -> str:
    desc = (task.description or "").strip()
    if desc:
        return f"（来源：任务描述）\n{desc}"
    return ""


def _downstream_hint(task: Task) -> str:
    name = (task.task_name or "").strip()
    desc = (task.description or "").strip()
    parts = []
    if name:
        parts.append(f"下游任务「{name}」需要关注上游产出。")
    if desc:
        parts.append(desc)
    return "\n".join(parts) if parts else ""


def _build_artifacts_markdown(result_json: dict | None) -> str:
    if not isinstance(result_json, dict):
        return ""
    artifacts = result_json.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        return ""
    lines = []
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        path = str(a.get("path", "")).strip()
        desc = str(a.get("description", "")).strip()
        atype = str(a.get("type", "")).strip()
        if not path:
            continue
        label = f"{desc} ({atype})" if desc and atype else (desc or atype or path)
        lines.append(f"- {label}: `{path}`")
    return "\n".join(lines)


# ——— 第 3 阶段：Handoff 渲染 ———


def render_handoff_draft(facts: dict, from_task: Task, to_task: Task) -> dict[str, str]:
    edge_type = facts.get("edge_type", "general")
    fact_map: dict[str, str] = facts.get("facts", {})

    # Summary：优先用 result.json 的 summary，否则用边类型前缀
    summary = fact_map.get("summary", "").strip()
    if not summary:
        summary = _EDGE_TYPE_SUMMARY_PREFIX.get(edge_type, _EDGE_TYPE_SUMMARY_PREFIX["general"])

    # Details：按渲染规格逐节输出，空内容跳过
    spec = _RENDER_SPECS.get(edge_type, _RENDER_SPECS["general"])
    sections: list[str] = []
    for heading, content_key in spec:
        content = fact_map.get(content_key, "").strip()
        if content:
            sections.append(f"{heading}\n{content}")

    details = "\n\n".join(sections) if sections else ""

    return {
        "summary": summary,
        "details": details,
    }


# ——— 第 4 阶段：校验 ———


def validate_draft(draft: dict[str, str], source_context: dict) -> list[str]:
    warnings: list[str] = []
    if not draft.get("summary", "").strip():
        warnings.append("summary 为空，建议手动补充")
    if not draft.get("details", "").strip():
        warnings.append("details 为空，无法提取有效信息")
    if source_context.get("result_json") is None:
        warnings.append("上游任务未找到 result.json，草稿内容可能不完整")
    if not source_context.get("report_files"):
        if not isinstance(source_context.get("result_json"), dict) or not str(
            source_context.get("result_json", {}).get("summary", "")
        ).strip():
            warnings.append("未找到可供提取的报告文件，草稿仅基于任务元数据")
    return warnings


# ——— 主编排 ———


def generate_auto_draft(
    db: Session, project: Project, from_task: Task, to_task: Task
) -> dict:
    source_context = build_source_context(db, project, from_task)
    extraction = extract_facts(source_context, from_task, to_task)
    draft = render_handoff_draft(extraction, from_task, to_task)
    validation_warnings = validate_draft(draft, source_context)

    all_warnings = (
        source_context.get("collection_warnings", [])
        + extraction.get("extraction_warnings", [])
        + validation_warnings
    )

    return {
        "draft": draft,
        "edge_type": extraction["edge_type"],
        "warnings": all_warnings,
        "source_info": {
            "result_json_found": source_context.get("result_json") is not None,
            "reports_read": list(source_context.get("report_files", {}).keys()),
            "from_task_code": from_task.task_code,
            "to_task_code": to_task.task_code,
        },
    }
