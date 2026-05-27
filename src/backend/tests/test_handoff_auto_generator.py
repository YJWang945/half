import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models import Task
from services.handoff_auto_generator import (
    _build_artifacts_markdown,
    _extract_sections_from_markdown,
    extract_facts,
    generate_auto_draft,
    infer_edge_type,
    render_handoff_draft,
    validate_draft,
)


def _make_task(code: str, name: str, description: str = "", status: str = "completed") -> Task:
    return Task(
        id=1,
        project_id=1,
        plan_id=1,
        task_code=code,
        task_name=name,
        description=description,
        status=status,
    )


class InferEdgeTypeTests(unittest.TestCase):
    def test_dev_to_test_by_code(self):
        self.assertEqual(
            infer_edge_type(_make_task("T1_DEV", ""), _make_task("T2_TEST", "")),
            "dev-to-test",
        )

    def test_dev_to_review_by_code(self):
        self.assertEqual(
            infer_edge_type(_make_task("T1_DEV", ""), _make_task("T3_REVIEW", "")),
            "dev-to-review",
        )

    def test_dev_to_review_by_chinese_name(self):
        self.assertEqual(
            infer_edge_type(
                _make_task("T1", "开发任务"),  # 开发任务
                _make_task("T3", "代码审查"),  # 代码审查
            ),
            "dev-to-review",
        )

    def test_test_to_revise_by_code(self):
        self.assertEqual(
            infer_edge_type(_make_task("T2_TEST", ""), _make_task("T5_FIX", "")),
            "test-to-revise",
        )

    def test_review_to_revise_by_code(self):
        self.assertEqual(
            infer_edge_type(_make_task("T3_REVIEW", ""), _make_task("T5_REVISE", "")),
            "review-to-revise",
        )

    def test_fallback_general(self):
        self.assertEqual(
            infer_edge_type(_make_task("T1_DOCS", ""), _make_task("T2_SYNC", "")),
            "general",
        )


class ExtractSectionsTests(unittest.TestCase):
    def test_extract_known_headings(self):
        md = (
            "## 核心变更\n"
            "修复登录重试限制\n\n"
            "## 测试重点\n"
            "验证锁定逻辑\n\n"
            "## 风险提示\n"
            "LDAP 分支未覆盖\n"
        )
        sections = _extract_sections_from_markdown(md)
        self.assertIn("core_changes", sections)
        self.assertIn("修复登录重试限制", sections["core_changes"])
        self.assertIn("test_focus", sections)
        self.assertIn("risks", sections)

    def test_unknown_heading_ignored(self):
        md = "## 随机标题\n无关内容"
        sections = _extract_sections_from_markdown(md)
        self.assertEqual(len(sections), 0)

    def test_handles_empty_markdown(self):
        sections = _extract_sections_from_markdown("")
        self.assertEqual(len(sections), 0)

    def test_multiple_sections_same_key(self):
        md = (
            "## 核心变更\nA\n\n"
            "## 其他变更\nB\n"
        )
        sections = _extract_sections_from_markdown(md)
        self.assertIn("core_changes", sections)
        self.assertIn("A", sections["core_changes"])
        self.assertIn("B", sections["core_changes"])


class ExtractFactsTests(unittest.TestCase):
    def test_extracts_from_result_json(self):
        source = {
            "result_json": {
                "task_code": "T1_DEV",
                "summary": "修复了登录 bug",
                "artifacts": [
                    {"path": "outputs/T1/report.md", "type": "report", "description": "开发报告"},
                ],
            },
            "report_files": {},
            "collection_warnings": [],
        }
        result = extract_facts(source, _make_task("T1_DEV", "开发"), _make_task("T2_TEST", "测试"))
        self.assertEqual(result["edge_type"], "dev-to-test")
        self.assertEqual(result["facts"].get("summary"), "修复了登录 bug")

    def test_fallback_when_no_report(self):
        source = {
            "result_json": None,
            "report_files": {},
            "collection_warnings": [],
        }
        from_task = _make_task("T1_DEV", "开发", "修复登录重试逻辑")
        to_task = _make_task("T2_TEST", "测试", "验证修复结果")
        result = extract_facts(source, from_task, to_task)
        self.assertEqual(result["edge_type"], "dev-to-test")
        self.assertIn("修复登录重试逻辑", result["facts"].get("core_changes", ""))
        self.assertIn("验证修复结果", result["facts"].get("test_focus", ""))


class BuildArtifactsMarkdownTests(unittest.TestCase):
    def test_builds_list(self):
        result_json = {
            "artifacts": [
                {"path": "outputs/T1/report.md", "type": "report", "description": "开发报告"},
            ]
        }
        md = _build_artifacts_markdown(result_json)
        self.assertIn("outputs/T1/report.md", md)
        self.assertIn("开发报告", md)

    def test_empty_when_no_artifacts(self):
        self.assertEqual(_build_artifacts_markdown(None), "")
        self.assertEqual(_build_artifacts_markdown({}), "")


class RenderHandoffDraftTests(unittest.TestCase):
    def test_dev_to_test_sections(self):
        extraction = {
            "edge_type": "dev-to-test",
            "facts": {
                "summary": "修复完成",
                "core_changes": "修复登录重试",
                "test_focus": "验证锁定逻辑",
                "risks": "LDAP 未覆盖",
                "artifacts_list": "- report.md",
            },
        }
        draft = render_handoff_draft(extraction, _make_task("T1", ""), _make_task("T2", ""))
        self.assertIn("修复完成", draft["summary"])
        self.assertIn("## 核心变更", draft["details"])
        self.assertIn("## 测试重点", draft["details"])
        self.assertIn("## 风险提示", draft["details"])

    def test_omits_empty_sections(self):
        extraction = {
            "edge_type": "dev-to-test",
            "facts": {
                "summary": "修复完成",
                "core_changes": "修复登录重试",
                "test_focus": "",
                "risks": "",
                "artifacts_list": "",
            },
        }
        draft = render_handoff_draft(extraction, _make_task("T1", ""), _make_task("T2", ""))
        self.assertIn("## 核心变更", draft["details"])
        self.assertNotIn("## 测试重点", draft["details"])
        self.assertNotIn("## 风险提检", draft["details"])

    def test_general_fallback(self):
        extraction = {
            "edge_type": "general",
            "facts": {
                "summary": "",
                "upstream_conclusion": "上游任务已完成",
            },
        }
        draft = render_handoff_draft(extraction, _make_task("T1", ""), _make_task("T2", ""))
        self.assertIn("上游任务已完成", draft["summary"])
        self.assertIn("## 上游结论", draft["details"])


class ValidateDraftTests(unittest.TestCase):
    def test_warns_empty_summary(self):
        warnings = validate_draft({"summary": "", "details": "x"}, {"result_json": None, "report_files": {}})
        self.assertTrue(any("summary" in w for w in warnings))

    def test_warns_empty_details(self):
        warnings = validate_draft({"summary": "ok", "details": ""}, {"result_json": None, "report_files": {}})
        self.assertTrue(any("details" in w for w in warnings))

    def test_warns_no_result_json(self):
        warnings = validate_draft({"summary": "ok", "details": "ok"}, {"result_json": None, "report_files": {}})
        self.assertTrue(any("result.json" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
