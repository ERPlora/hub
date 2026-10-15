// Types of the task app's operations for the SDK (`useLive`, `useCommand`), from apps/task/schemas.py.
// Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, ids travel in the input. Dates are ISO
// `YYYY-MM-DD`; moments, ISO date-times.
import type { Page } from '../../../frontend/sdk-types';

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'cancelled';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

type Both<K extends string> = K | `-${K}`;
export type TaskSort = Both<
  'number' | 'title' | 'status' | 'priority' | 'due_date' | 'completed_at' | 'created_at' | 'project_name' | 'assignee_name' | 'id'
>;
export type ProjectSort = Both<'code' | 'name' | 'color' | 'is_active' | 'owner_name' | 'task_count' | 'open_task_count' | 'created_at' | 'id'>;

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A task by id, or by its number or title. */
export interface TaskRefIn {
  id?: string | null;
  task?: string | null;
}

export interface TaskListIn extends PageIn {
  search?: string;
  number?: string;
  title?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  open?: boolean;
  overdue?: boolean;
  project_id?: string;
  project?: string;
  assigned_to_id?: string;
  assignee?: string;
  unassigned?: boolean;
  parent_id?: string;
  top_level?: boolean;
  tag?: string;
  due_from?: string;
  due_to?: string;
  completed_from?: string;
  completed_to?: string;
  created_from?: string;
  created_to?: string;
  sort?: TaskSort;
}

export interface TaskMineIn extends PageIn {
  search?: string;
  due_within_days?: number;
}

export interface SubtaskListIn extends PageIn, TaskRefIn {}

export interface TaskIn {
  title: string;
  description?: string;
  priority?: TaskPriority;
  due_date?: string | null;
  project_id?: string | null;
  project?: string | null;
  parent_id?: string | null;
  parent?: string | null;
  assigned_to_id?: string | null;
  assignee?: string | null;
  tags?: string[];
}

/** Only the fields sent change; `null` clears `due_date` and `project_id`. */
export interface TaskPatchIn extends TaskRefIn {
  title?: string;
  description?: string;
  priority?: TaskPriority;
  due_date?: string | null;
  project_id?: string | null;
  project?: string | null;
  tags?: string[];
}

export interface SetStatusIn extends TaskRefIn {
  status: TaskStatus;
}

/** One person (by id, by name or the caller); nobody unassigns. */
export interface AssignIn extends TaskRefIn {
  member_id?: string | null;
  member?: string | null;
  to_me?: boolean;
}

export interface TaskOut {
  id: string;
  number: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  project_id: string | null;
  project_name: string | null;
  project_color: string | null;
  parent_id: string | null;
  parent_number: string | null;
  parent_title: string | null;
  assigned_to_id: string | null;
  assignee_name: string | null;
  created_by_id: number | null;
  created_by_name: string | null;
  due_date: string | null;
  completed_at: string | null;
  tags: string[];
  subtask_count: number;
  comment_count: number;
  created_at: string;
  updated_at: string;
  can_change: boolean;
}

export interface CommentListIn extends PageIn {
  task_id?: string | null;
  task?: string | null;
}

export interface CommentIn {
  task_id?: string | null;
  task?: string | null;
  text: string;
}

export interface CommentOut {
  id: string;
  task_id: string;
  text: string;
  author_id: number | null;
  author_name: string | null;
  created_at: string;
}

export interface ProjectListIn extends PageIn {
  search?: string;
  code?: string;
  name?: string;
  color?: string;
  is_active?: boolean;
  owner_id?: string;
  sort?: ProjectSort;
}

export interface ProjectRefIn {
  id?: string | null;
  project?: string | null;
}

export interface ProjectIn {
  code: string;
  name: string;
  color?: string;
  owner_id?: string | null;
  owner?: string | null;
}

export interface ProjectPatchIn extends ProjectRefIn {
  name?: string;
  color?: string;
  is_active?: boolean;
  owner_id?: string | null;
  owner?: string | null;
}

export interface ProjectOut {
  id: string;
  code: string;
  name: string;
  color: string;
  is_active: boolean;
  owner_id: string | null;
  owner_name: string | null;
  task_count: number;
  open_task_count: number;
  created_at: string;
  updated_at: string;
}

export interface DeletedOut {
  id: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'task.task.list': { input: TaskListIn; output: Page<TaskOut> };
    'task.task.mine': { input: TaskMineIn; output: Page<TaskOut> };
    'task.task.detail': { input: TaskRefIn; output: TaskOut };
    'task.task.subtasks': { input: SubtaskListIn; output: Page<TaskOut> };
    'task.task.create': { input: TaskIn; output: TaskOut };
    'task.task.update': { input: TaskPatchIn; output: TaskOut };
    'task.task.set_status': { input: SetStatusIn; output: TaskOut };
    'task.task.complete': { input: TaskRefIn; output: TaskOut };
    'task.task.assign': { input: AssignIn; output: TaskOut };
    'task.task.delete': { input: TaskRefIn; output: DeletedOut };
    'task.comment.list': { input: CommentListIn; output: Page<CommentOut> };
    'task.comment.add': { input: CommentIn; output: CommentOut };
    'task.project.list': { input: ProjectListIn; output: Page<ProjectOut> };
    'task.project.detail': { input: ProjectRefIn; output: ProjectOut };
    'task.project.create': { input: ProjectIn; output: ProjectOut };
    'task.project.update': { input: ProjectPatchIn; output: ProjectOut };
    'task.project.delete': { input: ProjectRefIn; output: DeletedOut };
  }
}
