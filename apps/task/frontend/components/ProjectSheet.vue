<script setup lang="ts">
// TASK-F13 «Abrir y cambiar un proyecto» and TASK-F14 «Borrar un proyecto» (tasks#43): the project's
// name with its colour, Active or Inactive and its code; for whoever manages projects, Name and Color
// editable with Save (only what this person changed, so another person's save meanwhile is never
// overwritten; an untouched field follows the live project), Deactivate / Activate (which never sends
// what was typed and not saved) and Delete, asked first; the 50 most recent tasks of the project, with how many more the
// Tasks tab lists, and «Add task», which creates it inside the project. The project and its tasks are
// followed live; a refusal is painted inside the sheet, which stays open.
import { ConfirmDialog, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonInput, IonModal, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { STATUS_TONE } from '../lib/format';
import type { ProjectPatchIn } from '../operations';

/** How many of a project's tasks the sheet lists; the rest are in the Tasks tab. */
const PROJECT_TASKS = 50;

const props = defineProps<{ projectId: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const session = useSession();
const canManage = computed(() => session.can('task.manage_project'));
const canAdd = computed(() => session.can('task.add'));

const detail = useLive('task.project.detail', () => ({ id: props.projectId }));
const tasks = useLive('task.task.list', () => ({ project_id: props.projectId, sort: '-created_at' as const, limit: PROJECT_TASKS }));
const project = computed(() => (detail.data.value?.id === props.projectId ? detail.data.value : undefined));
const gone = computed(() => detail.error.value?.code === 'not_found');

const update = useCommand('task.project.update');
const createTask = useCommand('task.task.create');
const remove = useCommand('task.project.delete');
const busy = computed(() => update.pending.value || createTask.pending.value);

const editName = ref('');
const editColor = ref('');
/** The name and colour the inputs started from: what Save compares with. */
const base = ref({ name: '', color: '' });
const newTask = ref('');
const sheetError = ref<ApiError | null>(null);
const deleteOpen = ref(false);

// What the inputs start from: the project as it arrives, and as it is saved.
watch(
  () => project.value?.id,
  () => {
    editName.value = project.value?.name ?? '';
    editColor.value = project.value?.color ?? '';
    base.value = { name: editName.value, color: editColor.value };
    sheetError.value = null;
    newTask.value = '';
  },
  { immediate: true },
);
// Someone else saved it: an untouched field follows; what this person typed stays.
watch(
  () => [project.value?.name, project.value?.color] as const,
  ([name, color]) => {
    if (name === undefined || color === undefined) return;
    if (editName.value === base.value.name) editName.value = name;
    if (editColor.value === base.value.color) editColor.value = color;
    base.value = { name, color };
  },
);

async function send(changes: Omit<ProjectPatchIn, 'id' | 'project'>): Promise<void> {
  if (!project.value || busy.value) return;
  sheetError.value = null;
  try {
    const saved = await update.run({ id: project.value.id, ...changes });
    editName.value = saved.name;
    editColor.value = saved.color;
    base.value = { name: saved.name, color: saved.color };
  } catch {
    sheetError.value = update.error.value;
  }
}

/** Sends only what this person changed since the inputs started. */
function save(): void {
  const name = editName.value.trim();
  if (!project.value || !name) return;
  const changes: Omit<ProjectPatchIn, 'id' | 'project'> = {};
  if (name !== base.value.name.trim()) changes.name = name;
  if (editColor.value.trim() !== base.value.color.trim()) changes.color = editColor.value.trim();
  if (Object.keys(changes).length) void send(changes);
}

function toggleActive(): void {
  if (project.value) void send({ is_active: !project.value.is_active });
}

async function addTask(): Promise<void> {
  const sent = newTask.value;
  if (!project.value || !sent.trim() || busy.value) return;
  sheetError.value = null;
  try {
    await createTask.run({ title: sent.trim(), project_id: project.value.id });
  } catch {
    sheetError.value = createTask.error.value;
    return;
  }
  if (newTask.value === sent) newTask.value = '';
}

async function confirmDelete(): Promise<void> {
  if (!project.value) return;
  try {
    await remove.run({ id: project.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
  open.value = false;
}

const rows = computed(() => tasks.data.value?.rows ?? []);
const total = computed(() => tasks.data.value?.total ?? 0);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <ion-modal
    :is-open="open"
    data-testid="task-project-sheet"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>
          <span class="task-project-sheet__head">
            <span
              v-if="project?.color"
              class="task-project-sheet__swatch"
              :style="{ background: project.color }"
            />
            <span data-testid="task-project-sheet-title">{{ project?.name ?? t('task.loading') }}</span>
          </span>
        </ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="task-project-sheet-close"
            @click="open = false"
          >
            {{ t('task.actions.close') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <InlineFeedback
        v-if="gone"
        tone="warning"
        data-testid="task-project-sheet-gone"
      >
        {{ t('task.projects.sheet.gone') }}
      </InlineFeedback>
      <p
        v-else-if="!project"
        class="task-project-sheet__muted"
      >
        {{ t('task.loading') }}
      </p>
      <template v-if="project && !gone">
        <div class="task-project-sheet__line">
          <StatusPill
            data-testid="task-project-sheet-state"
            :tone="project.is_active ? 'success' : 'neutral'"
            :label="project.is_active ? t('task.projects.sheet.active') : t('task.projects.sheet.inactive')"
          />
          <span
            class="task-project-sheet__muted"
            data-testid="task-project-sheet-code"
          >{{ t('task.projects.sheet.code', { code: project.code }) }}</span>
        </div>
        <div
          v-if="canManage"
          class="task-project-sheet__row"
        >
          <ion-input
            data-testid="task-project-sheet-name"
            :value="editName"
            :label="t('task.projects.form.name')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="200"
            @ion-input="editName = text($event.detail.value)"
          />
          <ion-input
            data-testid="task-project-sheet-color"
            :value="editColor"
            :label="t('task.projects.form.color')"
            :placeholder="t('task.projects.form.colorPlaceholder')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="7"
            @ion-input="editColor = text($event.detail.value)"
          />
          <ion-button
            data-testid="task-project-sheet-save"
            size="small"
            :disabled="busy || !editName.trim()"
            @click="save"
          >
            {{ update.pending.value ? t('task.saving') : t('task.actions.save') }}
          </ion-button>
          <ion-button
            data-testid="task-project-sheet-toggle"
            size="small"
            fill="outline"
            :disabled="busy"
            @click="toggleActive"
          >
            {{ project.is_active ? t('task.actions.deactivate') : t('task.actions.activate') }}
          </ion-button>
          <ion-button
            data-testid="task-project-sheet-delete"
            size="small"
            fill="outline"
            color="danger"
            @click="(remove.error.value = null), (deleteOpen = true)"
          >
            {{ t('task.actions.delete') }}
          </ion-button>
        </div>
        <InlineFeedback
          v-if="sheetError"
          tone="danger"
          dismissible
          data-testid="task-project-sheet-error"
          :heading="t('task.tasks.rowError')"
          @dismiss="sheetError = null"
        >
          {{ sheetError.message }}
        </InlineFeedback>

        <h4 data-testid="task-project-sheet-tasks-heading">
          {{ t('task.projects.sheet.tasks', { count: total }) }}
        </h4>
        <p
          v-if="tasks.status.value === 'error'"
          class="task-project-sheet__error"
          data-testid="task-project-sheet-tasks-error"
        >
          {{ t('task.projects.sheet.tasksError') }}
        </p>
        <p
          v-else-if="!tasks.data.value"
          class="task-project-sheet__muted"
          data-testid="task-project-sheet-tasks-loading"
        >
          {{ t('task.loading') }}
        </p>
        <p
          v-else-if="!rows.length"
          class="task-project-sheet__muted"
          data-testid="task-project-sheet-tasks-empty"
        >
          {{ t('task.projects.sheet.empty') }}
        </p>
        <div
          v-for="row in rows"
          :key="row.id"
          class="task-project-sheet__task"
          :data-testid="`task-project-sheet-task-${row.id}`"
        >
          <span class="task-project-sheet__grow">{{ row.number }} — {{ row.title }}</span>
          <StatusPill
            size="sm"
            :tone="STATUS_TONE[row.status]"
            :label="t(`task.status.${row.status}`)"
          />
        </div>
        <p
          v-if="total > rows.length"
          class="task-project-sheet__muted"
          data-testid="task-project-sheet-more"
        >
          {{ t('task.projects.sheet.more', { shown: rows.length, total }) }}
        </p>
        <div
          v-if="canAdd"
          class="task-project-sheet__row"
        >
          <ion-input
            data-testid="task-project-sheet-new-task"
            :value="newTask"
            :label="t('task.actions.addTask')"
            :placeholder="t('task.projects.sheet.newTask')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="255"
            @ion-input="newTask = text($event.detail.value)"
            @keyup.enter="addTask"
          />
          <ion-button
            data-testid="task-project-sheet-add-task"
            size="small"
            :disabled="busy || !newTask.trim()"
            @click="addTask"
          >
            {{ t('task.actions.addTask') }}
          </ion-button>
        </div>
      </template>
    </ion-content>
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="task-project-sheet-delete-confirm"
      tone="danger"
      :title="t('task.projects.delete.title')"
      :message="project ? t('task.projects.delete.message', { name: project.name }) : ''"
      :confirm-label="t('task.projects.delete.confirm')"
      :cancel-label="t('task.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </ion-modal>
</template>

<style scoped>
.task-project-sheet__head {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.task-project-sheet__swatch {
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 50%;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  flex: none;
}
.task-project-sheet__line {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.task-project-sheet__muted {
  margin: 0;
  font-size: 0.9rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.task-project-sheet__error {
  margin: 0;
  color: var(--ion-color-danger, #c5000f);
  font-weight: 600;
}
.task-project-sheet__row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin: 8px 0 12px;
}
.task-project-sheet__row ion-input {
  flex: 1 1 11rem;
  min-width: 9rem;
}
.task-project-sheet__task {
  display: flex;
  gap: 10px;
  align-items: center;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
  padding: 6px 0;
}
.task-project-sheet__grow {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
h4 {
  margin: 16px 0 6px;
  font-size: 0.95rem;
}
</style>
