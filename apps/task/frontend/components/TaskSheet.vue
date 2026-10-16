<script setup lang="ts">
// TASK-F04 «Abrir una tarea» and the actions of its sheet (F05–F11): «TSK-… — Title» with its status and
// priority; the description; Due (red «Overdue», amber «Due today»), Completed, Assigned to, Project,
// Created and Created by; Status and Complete; Assign to (an active person, searched) with Assign,
// Assign to me and Unassign; Edit and Delete; the subtasks with Open (Back and the trail of numbers
// above) and «Add subtask»; the comments, newest first, signed and dated, and «Comment». The task, its
// subtasks and its comments are followed live. A box empties as soon as what it sent is accepted (only
// if nothing new was typed meanwhile, tasks#44); a refusal stays inside the sheet, with the text kept.
import { Combo, type ComboOption, ConfirmDialog, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonTextarea,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dueTone, formatDay, formatMoment, isClosed, PRIORITY_TONE, STATUS_TONE } from '../lib/format';
import { searchMembers } from '../lib/pickers';
import type { TaskStatus } from '../operations';
import TaskFormModal from './TaskFormModal.vue';

const STATUSES: readonly TaskStatus[] = ['todo', 'in_progress', 'blocked', 'done', 'cancelled'];

const props = defineProps<{ taskId: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const session = useSession();
const client = useLiveClient();
const findMembers = searchMembers(client);

/** The task on screen, and the parents opened on the way to it (for Back). */
const current = ref(props.taskId);
const trail = ref<Array<{ id: string; number: string }>>([]);
watch(
  () => props.taskId,
  (id) => {
    current.value = id;
    trail.value = [];
  },
);

const detail = useLive('task.task.detail', () => ({ id: current.value }));
const subtasks = useLive('task.task.subtasks', () => ({ id: current.value, limit: 100 }));
const comments = useLive('task.comment.list', () => ({ task_id: current.value, limit: 100 }));
const mine = useLive('staff.member.mine', {});

const task = computed(() => (detail.data.value?.id === current.value ? detail.data.value : undefined));
const gone = computed(() => detail.error.value?.code === 'not_found');
const myMemberId = computed(() => mine.data.value?.member?.id ?? null);
const canChange = computed(() => task.value?.can_change === true);
const canDelete = computed(() => session.can('task.delete'));

const setStatus = useCommand('task.task.set_status');
const complete = useCommand('task.task.complete');
const assign = useCommand('task.task.assign');
const createSubtask = useCommand('task.task.create');
const addComment = useCommand('task.comment.add');
const remove = useCommand('task.task.delete');
const busy = computed(() =>
  [setStatus, complete, assign, createSubtask, addComment].some((command) => command.pending.value),
);

const actionError = ref<ApiError | null>(null);
const assignTo = ref<ComboOption | null>(null);
const newSubtask = ref('');
const newComment = ref('');
const editOpen = ref(false);
const deleteOpen = ref(false);

watch(current, () => {
  actionError.value = null;
  assignTo.value = null;
  newSubtask.value = '';
  newComment.value = '';
});

/** Runs a command of the sheet; `accepted` runs as soon as the hub says yes. */
async function act(command: { run: (input: never) => Promise<unknown>; error: { value: ApiError | null } }, input: unknown, accepted?: () => void) {
  actionError.value = null;
  try {
    await command.run(input as never);
  } catch {
    actionError.value = command.error.value;
    return;
  }
  accepted?.();
}

function changeStatus(status: TaskStatus): void {
  if (!task.value || status === task.value.status) return;
  void act(setStatus, { id: task.value.id, status });
}

function doAssign(input: { member_id?: string; to_me?: boolean }): void {
  if (!task.value) return;
  void act(assign, { id: task.value.id, ...input }, () => {
    assignTo.value = null;
  });
}

function addSub(): void {
  const sent = newSubtask.value;
  if (!task.value || !sent.trim()) return;
  void act(createSubtask, { title: sent.trim(), parent_id: task.value.id }, () => {
    if (newSubtask.value === sent) newSubtask.value = '';
  });
}

function addNewComment(): void {
  const sent = newComment.value;
  if (!task.value || !sent.trim()) return;
  void act(addComment, { task_id: task.value.id, text: sent.trim() }, () => {
    if (newComment.value === sent) newComment.value = '';
  });
}

function drillDown(id: string): void {
  if (task.value) trail.value = [...trail.value, { id: task.value.id, number: task.value.number }];
  current.value = id;
}

function goBack(): void {
  const parent = trail.value.at(-1);
  if (!parent) return;
  trail.value = trail.value.slice(0, -1);
  current.value = parent.id;
}

async function confirmDelete(): Promise<void> {
  if (!task.value) return;
  try {
    await remove.run({ id: task.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
  if (trail.value.length) goBack();
  else open.value = false;
}

const dueLabel = computed(() => {
  const tone = task.value ? dueTone(task.value.due_date, task.value.status) : 'none';
  return tone === 'none' ? undefined : t(tone === 'overdue' ? 'task.due.overdue' : 'task.due.today');
});
const dueClass = computed(() => (task.value ? `task-sheet__due--${dueTone(task.value.due_date, task.value.status)}` : ''));
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <ion-modal
    :is-open="open"
    data-testid="task-sheet"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-button
            v-if="trail.length"
            data-testid="task-sheet-back"
            @click="goBack"
          >
            ← {{ t('task.actions.back') }}
          </ion-button>
        </ion-buttons>
        <ion-title data-testid="task-sheet-title">
          {{ task ? `${task.number} — ${task.title}` : t('task.loading') }}
        </ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="task-sheet-close"
            @click="open = false"
          >
            {{ t('task.actions.close') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <p
        v-if="trail.length && task"
        class="task-sheet__muted"
        data-testid="task-sheet-trail"
      >
        {{ [...trail.map((step) => step.number), task.number].join(' › ') }}
      </p>
      <InlineFeedback
        v-if="gone"
        tone="warning"
        data-testid="task-sheet-gone"
      >
        {{ t('task.sheet.gone') }}
      </InlineFeedback>
      <InlineFeedback
        v-else-if="detail.status.value === 'error'"
        tone="danger"
        data-testid="task-sheet-load-error"
        :heading="t('task.sheet.loadError')"
      >
        {{ detail.error.value?.message }}
      </InlineFeedback>
      <p
        v-else-if="!task"
        class="task-sheet__muted"
        data-testid="task-sheet-loading"
      >
        {{ t('task.loading') }}
      </p>
      <template v-if="task && !gone">
        <div class="task-sheet__pills">
          <StatusPill
            :tone="STATUS_TONE[task.status]"
            :label="t(`task.status.${task.status}`)"
          />
          <StatusPill
            :tone="PRIORITY_TONE[task.priority]"
            :dot="false"
            :label="t(`task.priority.${task.priority}`)"
          />
        </div>
        <p
          v-if="task.description"
          class="task-sheet__description"
          data-testid="task-sheet-description"
        >
          {{ task.description }}
        </p>
        <div class="task-sheet__meta">
          <span data-testid="task-sheet-due"><strong>{{ t('task.sheet.due') }}</strong> <span
            data-testid="task-sheet-due-value"
            :class="dueClass"
            :aria-label="dueLabel"
            :title="dueLabel"
          >{{ formatDay(task.due_date, locale) }}</span></span>
          <span data-testid="task-sheet-completed"><strong>{{ t('task.sheet.completed') }}</strong> {{ formatMoment(task.completed_at, locale) }}</span>
          <span data-testid="task-sheet-assignee"><strong>{{ t('task.sheet.assignedTo') }}</strong> {{ task.assignee_name ?? t('task.sheet.unassigned') }}</span>
          <span data-testid="task-sheet-project"><strong>{{ t('task.sheet.project') }}</strong> {{ task.project_name ?? '—' }}</span>
          <span data-testid="task-sheet-created"><strong>{{ t('task.sheet.created') }}</strong> {{ formatMoment(task.created_at, locale) }}</span>
          <span data-testid="task-sheet-created-by"><strong>{{ t('task.sheet.createdBy') }}</strong> {{ task.created_by_name ?? '—' }}</span>
        </div>

        <div class="task-sheet__actions">
          <ion-select
            data-testid="task-sheet-status"
            :value="task.status"
            :label="t('task.columns.status')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :disabled="busy || !canChange"
            @ion-change="changeStatus($event.detail.value as TaskStatus)"
          >
            <ion-select-option
              v-for="status in STATUSES"
              :key="status"
              :value="status"
            >
              {{ t(`task.status.${status}`) }}
            </ion-select-option>
          </ion-select>
          <ion-button
            data-testid="task-sheet-complete"
            size="small"
            color="success"
            :disabled="busy || !canChange || isClosed(task.status)"
            @click="act(complete, { id: task.id })"
          >
            {{ t('task.actions.complete') }}
          </ion-button>
        </div>
        <div class="task-sheet__actions">
          <Combo
            testid="task-sheet-assign-to"
            :model-value="assignTo"
            :search="findMembers"
            :label="t('task.sheet.assignTo')"
            :placeholder="t('task.sheet.pickPerson')"
            :disabled="busy || !canChange"
            @update:model-value="assignTo = $event"
          />
          <ion-button
            data-testid="task-sheet-assign"
            size="small"
            :disabled="busy || !canChange || !assignTo"
            @click="assignTo && doAssign({ member_id: assignTo.id })"
          >
            {{ t('task.actions.assign') }}
          </ion-button>
          <ion-button
            v-if="myMemberId && myMemberId !== task.assigned_to_id"
            data-testid="task-sheet-assign-me"
            size="small"
            fill="outline"
            :disabled="busy || !canChange"
            @click="doAssign({ to_me: true })"
          >
            {{ t('task.actions.assignToMe') }}
          </ion-button>
          <ion-button
            v-if="task.assigned_to_id"
            data-testid="task-sheet-unassign"
            size="small"
            fill="outline"
            color="medium"
            :disabled="busy || !canChange"
            @click="doAssign({})"
          >
            {{ t('task.actions.unassign') }}
          </ion-button>
        </div>
        <div class="task-sheet__actions">
          <ion-button
            v-if="canChange"
            data-testid="task-sheet-edit"
            size="small"
            fill="outline"
            @click="editOpen = true"
          >
            {{ t('task.actions.edit') }}
          </ion-button>
          <ion-button
            v-if="canDelete"
            data-testid="task-sheet-delete"
            size="small"
            fill="outline"
            color="danger"
            @click="(remove.error.value = null), (deleteOpen = true)"
          >
            {{ t('task.actions.delete') }}
          </ion-button>
        </div>
        <InlineFeedback
          v-if="actionError"
          tone="danger"
          dismissible
          data-testid="task-sheet-error"
          :heading="t('task.tasks.rowError')"
          @dismiss="actionError = null"
        >
          {{ actionError.message }}
        </InlineFeedback>

        <h4 data-testid="task-sheet-subtasks-heading">
          {{ t('task.sheet.subtasks', { count: subtasks.data.value?.total ?? task.subtask_count }) }}
        </h4>
        <div
          v-for="sub in subtasks.data.value?.rows ?? []"
          :key="sub.id"
          class="task-sheet__row"
          :data-testid="`task-sheet-subtask-${sub.id}`"
        >
          <span class="task-sheet__grow">{{ sub.number }} — {{ sub.title }}</span>
          <StatusPill
            size="sm"
            :tone="STATUS_TONE[sub.status]"
            :label="t(`task.status.${sub.status}`)"
          />
          <ion-button
            :data-testid="`task-sheet-subtask-open-${sub.id}`"
            size="small"
            fill="clear"
            @click="drillDown(sub.id)"
          >
            {{ t('task.actions.open') }}
          </ion-button>
        </div>
        <p
          v-if="subtasks.data.value && !subtasks.data.value.rows.length"
          class="task-sheet__muted"
          data-testid="task-sheet-subtasks-empty"
        >
          {{ t('task.sheet.emptySubtasks') }}
        </p>
        <div class="task-sheet__compose">
          <ion-input
            data-testid="task-sheet-new-subtask"
            :value="newSubtask"
            :label="t('task.actions.addSubtask')"
            :placeholder="t('task.sheet.newSubtask')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="255"
            @ion-input="newSubtask = text($event.detail.value)"
            @keyup.enter="addSub"
          />
          <ion-button
            data-testid="task-sheet-add-subtask"
            size="small"
            :disabled="busy || !canChange || !newSubtask.trim()"
            @click="addSub"
          >
            {{ t('task.actions.addSubtask') }}
          </ion-button>
        </div>

        <h4 data-testid="task-sheet-comments-heading">
          {{ t('task.sheet.comments', { count: comments.data.value?.total ?? task.comment_count }) }}
        </h4>
        <div
          v-for="comment in comments.data.value?.rows ?? []"
          :key="comment.id"
          class="task-sheet__comment"
          :data-testid="`task-sheet-comment-${comment.id}`"
        >
          <div class="task-sheet__muted">
            {{ comment.author_name ?? t('task.sheet.anonymous') }} · {{ formatMoment(comment.created_at, locale) }}
          </div>
          <p>{{ comment.text }}</p>
        </div>
        <p
          v-if="comments.data.value && !comments.data.value.rows.length"
          class="task-sheet__muted"
          data-testid="task-sheet-comments-empty"
        >
          {{ t('task.sheet.emptyComments') }}
        </p>
        <div class="task-sheet__compose">
          <ion-textarea
            data-testid="task-sheet-new-comment"
            :value="newComment"
            :label="t('task.actions.comment')"
            :placeholder="t('task.sheet.addComment')"
            label-placement="floating"
            fill="outline"
            mode="md"
            auto-grow
            :rows="1"
            :maxlength="5000"
            @ion-input="newComment = text($event.detail.value)"
          />
          <ion-button
            data-testid="task-sheet-add-comment"
            size="small"
            :disabled="busy || !canChange || !newComment.trim()"
            @click="addNewComment"
          >
            {{ t('task.actions.comment') }}
          </ion-button>
        </div>
      </template>
    </ion-content>
    <TaskFormModal
      v-model:open="editOpen"
      :task="task ?? null"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="task-sheet-delete-confirm"
      tone="danger"
      :title="t('task.delete.title')"
      :message="task ? t('task.delete.message', { name: `${task.number} ${task.title}` }) : ''"
      :confirm-label="t('task.delete.confirm')"
      :cancel-label="t('task.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </ion-modal>
</template>

<style scoped>
.task-sheet__muted {
  margin: 0 0 8px;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.task-sheet__pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.task-sheet__description {
  white-space: pre-wrap;
  margin: 4px 0 12px;
}
.task-sheet__meta {
  display: flex;
  gap: 8px 20px;
  flex-wrap: wrap;
  font-size: 0.9rem;
  margin-bottom: 12px;
}
.task-sheet__due--overdue {
  color: var(--ion-color-danger, #c5000f);
  font-weight: 600;
}
.task-sheet__due--today {
  color: var(--ion-color-warning-shade, #b37400);
  font-weight: 600;
}
.task-sheet__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin: 8px 0;
}
.task-sheet__actions ion-select,
.task-sheet__actions > :deep(.combo) {
  flex: 1 1 11rem;
  min-width: 9rem;
}
.task-sheet__row {
  display: flex;
  gap: 10px;
  align-items: center;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  padding: 6px 0;
}
.task-sheet__grow {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.task-sheet__comment {
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  padding: 6px 0;
}
.task-sheet__comment p {
  margin: 0;
  white-space: pre-wrap;
}
.task-sheet__compose {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  margin-top: 8px;
}
.task-sheet__compose ion-input,
.task-sheet__compose ion-textarea {
  flex: 1;
}
h4 {
  margin: 16px 0 6px;
  font-size: 0.95rem;
}
</style>
