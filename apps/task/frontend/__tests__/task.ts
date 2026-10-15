// A task row as the server sends it (`TaskOut`), for the page and component tests.
import type { TaskOut } from '../operations';

export function task(over: Partial<TaskOut> = {}): TaskOut {
  return {
    id: 't1',
    number: 'TSK-20261015-0001',
    title: 'Clean the store room',
    description: '',
    status: 'todo',
    priority: 'medium',
    project_id: null,
    project_name: null,
    project_color: null,
    parent_id: null,
    parent_number: null,
    parent_title: null,
    assigned_to_id: null,
    assignee_name: null,
    created_by_id: 1,
    created_by_name: 'Marta Jefa',
    due_date: null,
    completed_at: null,
    tags: [],
    subtask_count: 0,
    comment_count: 0,
    created_at: '2026-10-15T08:00:00Z',
    updated_at: '2026-10-15T08:00:00Z',
    can_change: true,
    ...over,
  };
}
