import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { Task, Agent, Project, TaskHandoff } from '../types';
import DagView from '../components/DagView';
import TaskDetailPanel from '../components/TaskDetailPanel';
import { getNextStepText } from '../contracts';

export default function TasksPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [handoffs, setHandoffs] = useState<TaskHandoff[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const lastFetchAtRef = React.useRef<number>(0);

  const fetchData = useCallback(async () => {
    lastFetchAtRef.current = Date.now();
    // 跨页面共享的 /api/agents、/api/projects/:id 走 stale-while-revalidate 缓存：
    // 命中时立刻渲染旧值，再后台刷新；这样切回任务页时不会再整页白屏。
    void api.getCached<Agent[]>('/api/agents', (value) => setAgents(value));
    void api.getCached<Project>(`/api/projects/${id}`, (value) => {
      setProject(value);
      setLoading(false);
    });
    try {
      const [taskList, handoffList] = await Promise.all([
        api.get<Task[]>(`/api/projects/${id}/tasks`),
        api.get<TaskHandoff[]>(`/api/projects/${id}/handoffs`),
      ]);
      setTasks(taskList);
      setHandoffs(handoffList);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const hasActiveWork = Boolean(
      project && ['planning', 'executing'].includes(project.status)
    ) || tasks.some((task) => task.status === 'running');
    if (!hasActiveWork) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void fetchData();
    }, 5000);

    return () => window.clearInterval(timer);
  }, [fetchData, project, tasks]);

  useEffect(() => {
    // focus / visibilitychange 上的刷新做 2s 节流，避免与 5s 轮询、
    // React StrictMode 双调用、以及快速切页叠加在一起。
    const THROTTLE_MS = 2000;
    const maybeRefresh = () => {
      if (Date.now() - lastFetchAtRef.current < THROTTLE_MS) return;
      void fetchData();
    };
    const refreshOnFocus = () => maybeRefresh();
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') maybeRefresh();
    };

    window.addEventListener('focus', refreshOnFocus);
    document.addEventListener('visibilitychange', refreshOnVisible);
    return () => {
      window.removeEventListener('focus', refreshOnFocus);
      document.removeEventListener('visibilitychange', refreshOnVisible);
    };
  }, [fetchData]);

  async function handleManualRefresh() {
    setRefreshing(true);
    try {
      await api.post(`/api/projects/${id}/poll`);
      await fetchData();
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
    }
  }

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || null;
  const nextStepText = getNextStepText(project?.next_step);
  const tasksWithAgentLabels = tasks.map((task) => {
    const assignee = agents.find((agent) => agent.id === task.assignee_agent_id);
    return {
      ...task,
      assignee_label: assignee ? assignee.name : null,
    };
  });

  if (loading) return <div className="page-loading">正在加载任务...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>计划修改与执行</h1>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={handleManualRefresh}
            disabled={refreshing}
            title="主动轮询后端状态，刷新任务进度和项目状态"
          >
            {refreshing ? '刷新中...' : '手动刷新'}
          </button>
          <button className="btn btn-ghost" onClick={() => navigate(`/projects/${id}`)} title="返回项目详情页">
            返回项目
          </button>
        </div>
      </div>

      {nextStepText && (
        <div className="next-step-banner">
          <strong>下一步：</strong> {nextStepText}
        </div>
      )}

      <div className="tasks-layout">
        <div className="tasks-dag-panel">
          <DagView
            tasks={tasksWithAgentLabels}
            handoffs={handoffs}
            selectedTaskId={selectedTaskId}
            onSelectTask={setSelectedTaskId}
            missingPredecessorIds={new Set()}
          />
        </div>
        <div className="tasks-detail-panel">
          {selectedTask ? (
            <TaskDetailPanel
              task={selectedTask}
              agents={agents}
              allTasks={tasks}
              handoffs={handoffs}
              onRefresh={fetchData}
            />
          ) : (
            <div className="empty-panel">
              <p>请选择左侧任务节点以查看详情。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
