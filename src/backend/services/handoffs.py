import json
from typing import Any

from sqlalchemy.orm import Session

from models import Task, TaskHandoff


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def build_handoff_document(
    from_task_code: str,
    to_task_code: str,
    *,
    summary: Any = "",
    details: Any = "",
) -> dict[str, object]:
    return {
        "from_task_id": _normalize_text(from_task_code),
        "to_task_id": _normalize_text(to_task_code),
        "summary": _normalize_text(summary),
        "details": _normalize_text(details),
    }


def default_handoff_document(from_task: Task, to_task: Task) -> dict[str, object]:
    return build_handoff_document(from_task.task_code, to_task.task_code)


def parse_handoff_document(handoff_json: str | None, from_task: Task, to_task: Task) -> dict[str, object]:
    if not handoff_json:
        return default_handoff_document(from_task, to_task)
    try:
        parsed = json.loads(handoff_json)
    except json.JSONDecodeError:
        return default_handoff_document(from_task, to_task)
    if not isinstance(parsed, dict):
        return default_handoff_document(from_task, to_task)
    try:
        return build_handoff_document(
            from_task.task_code,
            to_task.task_code,
            summary=parsed.get("summary"),
            details=parsed.get("details"),
        )
    except ValueError:
        return default_handoff_document(from_task, to_task)


def handoff_has_content(document: dict[str, object]) -> bool:
    if _normalize_text(document.get("summary")):
        return True
    if _normalize_text(document.get("details")):
        return True
    return False


def serialize_handoff_document(document: dict[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False)


def ensure_handoffs_for_tasks(db: Session, tasks: list[Task]) -> list[TaskHandoff]:
    if not tasks:
        return []
    task_by_code = {task.task_code: task for task in tasks if task.task_code}
    project_id = tasks[0].project_id
    created: list[TaskHandoff] = []
    existing = {
        (handoff.from_task_id, handoff.to_task_id)
        for handoff in db.query(TaskHandoff).filter(TaskHandoff.project_id == project_id).all()
    }
    for task in tasks:
        try:
            depends_on = json.loads(task.depends_on_json or "[]")
        except json.JSONDecodeError:
            depends_on = []
        if not isinstance(depends_on, list):
            continue
        for dep_code in depends_on:
            predecessor = task_by_code.get(str(dep_code))
            if predecessor is None:
                continue
            edge = (predecessor.id, task.id)
            if edge in existing:
                continue
            handoff = TaskHandoff(
                project_id=project_id,
                from_task_id=predecessor.id,
                to_task_id=task.id,
                handoff_json=serialize_handoff_document(default_handoff_document(predecessor, task)),
            )
            db.add(handoff)
            created.append(handoff)
            existing.add(edge)
    return created


# ——— Handoff 模板预设 ———

HANDOFF_TEMPLATES: dict[str, dict[str, str]] = {
    "dev-to-test": {
        "label": "开发 → 测试",
        "summary_prefix": "已完成代码修改并通过本地验证。",
        "details_template": (
            "## 核心变更\n"
            "（描述本次修改的核心内容和涉及文件）\n\n"
            "## 测试重点\n"
            "- 验证 Bug 是否按修改方案被修复\n"
            "- 检查本次改动影响的相邻功能是否出现回归\n\n"
            "## 风险提示\n"
            "- （填写已知风险或边界说明）\n"
        ),
    },
    "dev-to-review": {
        "label": "开发 → 评审",
        "summary_prefix": "代码实现已完成，请围绕修复范围和边界条件进行专项审查。",
        "details_template": (
            "## 修改范围\n"
            "（描述本次修改的范围和涉及模块）\n\n"
            "## 评审要点\n"
            "- 修改是否严格落在问题定位范围内\n"
            "- 是否引入了新的状态分支或未覆盖的异常路径\n\n"
            "## 注意事项\n"
            "- （填写评审时需特别关注的方面）\n"
        ),
    },
    "general": {
        "label": "通用交接",
        "summary_prefix": "上游任务已完成。",
        "details_template": (
            "## 上游结论\n"
            "（填写上游任务的核心结论）\n\n"
            "## 下游需关注\n"
            "- （填写下游必须了解的关键信息）\n\n"
            "## 风险 / 未决问题\n"
            "- （填写已知风险或待确认事项）\n"
        ),
    },
}


def generate_handoff_from_template(
    from_task_code: str,
    to_task_code: str,
    template_key: str,
) -> dict[str, object]:
    template = HANDOFF_TEMPLATES.get(template_key, HANDOFF_TEMPLATES["general"])
    return build_handoff_document(
        from_task_code,
        to_task_code,
        summary=template["summary_prefix"],
        details=template["details_template"],
    )
