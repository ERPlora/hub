// A project row as the server sends it (`ProjectOut`), for the page and component tests.
import type { ProjectOut } from '../operations';

export function project(over: Partial<ProjectOut> = {}): ProjectOut {
  return {
    id: 'p1',
    code: 'opening',
    name: 'Opening',
    color: '#AA3300',
    is_active: true,
    owner_id: null,
    owner_name: null,
    task_count: 2,
    open_task_count: 1,
    created_at: '2026-10-15T08:00:00Z',
    updated_at: '2026-10-15T08:00:00Z',
    ...over,
  };
}
