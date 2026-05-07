import { describe, expect, it, vi } from 'vitest';

import {
  getUnavailableAgentSelectionMessage,
  isUnavailableAgentSelectionDisabled,
  triggerAgentCardToggle,
  triggerAgentCardToggleFromKey,
} from './ProjectNewPage';
import type { Agent } from '../types';

function makeAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: 1,
    name: '默认 Agent',
    slug: 'default-agent',
    agent_type: 'claude',
    model_name: 'claude-sonnet',
    models: [{ model_name: 'claude-sonnet', capability: '分析' }],
    capability: '分析',
    co_located: false,
    is_active: true,
    availability_status: 'available',
    display_order: 0,
    subscription_expires_at: '2099-05-01 12:00',
    short_term_reset_at: null,
    short_term_reset_interval_hours: null,
    short_term_reset_needs_confirmation: false,
    long_term_reset_at: null,
    long_term_reset_interval_days: null,
    long_term_reset_mode: 'days',
    long_term_reset_needs_confirmation: false,
    ...overrides,
  };
}

describe('ProjectNewPage unavailable agent logic', () => {
  it('marks newly selected unavailable agents as disabled', () => {
    const unavailableAgent = makeAgent({
      id: 2,
      name: '不可用 Agent',
      subscription_expires_at: '2026-04-01 00:00',
    });

    expect(isUnavailableAgentSelectionDisabled(unavailableAgent, [])).toBe(true);
  });

  it('keeps originally selected unavailable agents enabled in edit mode', () => {
    const unavailableAgent = makeAgent({
      id: 3,
      name: '已保留不可用 Agent',
      subscription_expires_at: '2026-04-01 00:00',
    });

    expect(isUnavailableAgentSelectionDisabled(unavailableAgent, [3])).toBe(false);
  });

  it('builds a chinese error message with unavailable agent names', () => {
    expect(
      getUnavailableAgentSelectionMessage([
        makeAgent({ id: 2, name: 'Agent A' }),
        makeAgent({ id: 3, name: 'Agent B' }),
      ])
    ).toBe('不可用的 Agent 无法参与项目：Agent A、Agent B');
  });

  it('does not trigger click toggle handlers for disabled cards', () => {
    const onToggle = vi.fn();

    triggerAgentCardToggle(true, onToggle);

    expect(onToggle).not.toHaveBeenCalled();
  });

  it('does not trigger keyboard toggle handlers for disabled or unrelated keys', () => {
    const onToggle = vi.fn();

    expect(triggerAgentCardToggleFromKey('Enter', true, onToggle)).toBe(false);
    expect(triggerAgentCardToggleFromKey('Escape', false, onToggle)).toBe(false);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('triggers keyboard toggle handlers for enabled enter and space keys', () => {
    const onToggle = vi.fn();

    expect(triggerAgentCardToggleFromKey('Enter', false, onToggle)).toBe(true);
    expect(triggerAgentCardToggleFromKey(' ', false, onToggle)).toBe(true);
    expect(onToggle).toHaveBeenCalledTimes(2);
  });
});
