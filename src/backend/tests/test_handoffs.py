import json
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database
from auth import hash_password
from models import Base, Project, Task, TaskHandoff, User
from routers import auth as auth_router
from routers import handoffs as handoffs_router
from services.handoffs import serialize_handoff_document


class HandoffApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        app = FastAPI()
        app.include_router(auth_router.router)
        app.include_router(handoffs_router.router)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[database.get_db] = override_get_db
        self.client = TestClient(app)

        with self.SessionLocal() as db:
            owner = User(username="owner", password_hash=hash_password("Owner123"))
            other = User(username="other", password_hash=hash_password("Other123"))
            db.add_all([owner, other])
            db.flush()

            project = Project(name="demo-project", created_by=owner.id)
            other_project = Project(name="other-project", created_by=other.id)
            db.add_all([project, other_project])
            db.flush()

            upstream = Task(project_id=project.id, plan_id=1, task_code="T1", task_name="开发", status="completed")
            downstream = Task(project_id=project.id, plan_id=1, task_code="T2", task_name="测试", status="pending", depends_on_json='["T1"]')
            outsider_upstream = Task(project_id=other_project.id, plan_id=2, task_code="O1", task_name="外部开发", status="completed")
            outsider_downstream = Task(project_id=other_project.id, plan_id=2, task_code="O2", task_name="外部测试", status="pending", depends_on_json='["O1"]')
            db.add_all([upstream, downstream, outsider_upstream, outsider_downstream])
            db.flush()

            db.add(TaskHandoff(
                project_id=project.id,
                from_task_id=upstream.id,
                to_task_id=downstream.id,
                handoff_json=serialize_handoff_document({
                    "from_task_id": "T1",
                    "to_task_id": "T2",
                    "summary": "请重点验证修复后的登录失败重试限制。",
                    "required_inputs": ["检查登录失败 5 次锁定是否生效"],
                    "artifacts": [
                        {
                            "path": "outputs/T1/report.md",
                            "type": "report",
                            "description": "开发报告",
                        }
                    ],
                    "open_questions": [],
                    "risks_or_caveats": ["LDAP 分支未覆盖"],
                }),
            ))
            db.add(TaskHandoff(
                project_id=other_project.id,
                from_task_id=outsider_upstream.id,
                to_task_id=outsider_downstream.id,
                handoff_json='{"from_task_id":"O1","to_task_id":"O2","summary":"","required_inputs":[],"artifacts":[],"open_questions":[],"risks_or_caveats":[]}',
            ))
            db.commit()

    def _headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def test_list_project_handoffs_returns_edge_schema(self):
        response = self.client.get("/api/projects/1/handoffs", headers=self._headers("owner", "Owner123"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["from_task_id"], "T1")
        self.assertEqual(payload[0]["to_task_id"], "T2")
        self.assertTrue(payload[0]["has_content"])
        self.assertEqual(payload[0]["artifacts"][0]["path"], "outputs/T1/report.md")

    def test_update_handoff_rewrites_document(self):
        response = self.client.put(
            "/api/handoffs/1",
            json={
                "summary": "请基于最新补丁执行回归。",
                "required_inputs": ["验证登录失败处理", "验证成功登录路径"],
                "artifacts": [{"path": "outputs/T1/report-v2.md", "type": "report", "description": "更新后的开发报告"}],
                "open_questions": ["旧配置是否仍在生产启用"],
                "risks_or_caveats": ["短信验证码链路未覆盖"],
            },
            headers=self._headers("owner", "Owner123"),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"], "请基于最新补丁执行回归。")
        self.assertEqual(payload["required_inputs"][1], "验证成功登录路径")
        self.assertEqual(payload["open_questions"][0], "旧配置是否仍在生产启用")

        with self.SessionLocal() as db:
            handoff = db.query(TaskHandoff).filter(TaskHandoff.id == 1).one()
            stored = json.loads(handoff.handoff_json)
            self.assertEqual(stored["artifacts"][0]["path"], "outputs/T1/report-v2.md")

    def test_owner_cannot_access_other_users_handoffs(self):
        response = self.client.get("/api/projects/2/handoffs", headers=self._headers("owner", "Owner123"))
        self.assertEqual(response.status_code, 404)

        response = self.client.put(
            "/api/handoffs/2",
            json={"summary": "x", "required_inputs": [], "artifacts": [], "open_questions": [], "risks_or_caveats": []},
            headers=self._headers("owner", "Owner123"),
        )
        self.assertEqual(response.status_code, 404)

    def test_generate_auto_draft_returns_draft_structure(self):
        response = self.client.post(
            "/api/handoffs/1/generate-auto-draft",
            headers=self._headers("owner", "Owner123"),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("draft", payload)
        self.assertIn("summary", payload["draft"])
        self.assertIn("details", payload["draft"])
        self.assertIn("edge_type", payload)
        self.assertIn("warnings", payload)
        self.assertIn("source_info", payload)
        self.assertIn("result_json_found", payload["source_info"])

    def test_generate_auto_draft_does_not_save(self):
        response = self.client.post(
            "/api/handoffs/1/generate-auto-draft",
            headers=self._headers("owner", "Owner123"),
        )
        self.assertEqual(response.status_code, 200)

        with self.SessionLocal() as db:
            handoff = db.query(TaskHandoff).filter(TaskHandoff.id == 1).one()
            stored = json.loads(handoff.handoff_json)
        self.assertEqual(stored.get("summary"), "请重点验证修复后的登录失败重试限制。")

    def test_generate_auto_draft_404_for_wrong_owner(self):
        response = self.client.post(
            "/api/handoffs/2/generate-auto-draft",
            headers=self._headers("owner", "Owner123"),
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
