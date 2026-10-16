<script setup lang="ts">
// TASK-F01 «Crear una tarea» and TASK-F08 «Editar una tarea»: «New task» asks for Title (required),
// Description, Priority (Medium), Due, Assigned to (an active person of the team, searched on the
// server), Project (an active one) and Tags (separated by commas); «Edit» opens «Editing task —
// {number}» with the task loaded and sends only what this person changed against the copy taken when it
// opened, never against the live task (another person's save meanwhile is never overwritten; the
// assignee has its own buttons in the task's sheet). Refusals stay in the dialog, under their field;
// what was typed stays.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { parseTags, tagsText } from '../lib/format';
import { searchMembers, searchProjects } from '../lib/pickers';
import type { TaskOut, TaskPatchIn, TaskPriority } from '../operations';

const PRIORITIES: readonly TaskPriority[] = ['low', 'medium', 'high', 'urgent'];

const props = defineProps<{
  /** The task being edited; `null` = «New task». */
  task: TaskOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface Form {
  title: string;
  description: string;
  priority: TaskPriority;
  due: string;
  assignee: ComboOption | null;
  project: ComboOption | null;
  tags: string;
}

const t = useT();
const client = useLiveClient();
const creation = useCommand('task.task.create');
const update = useCommand('task.task.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.task ? update.error.value : creation.error.value));
const title = computed(() => (props.task ? t('task.form.titleEdit', { number: props.task.number }) : t('task.form.titleNew')));
const form = ref<Form>(fromTask(null));
/** The form as it opened: what an edit is compared with. */
const original = ref<Form>(fromTask(null));
const findMembers = searchMembers(client);
const findProjects = searchProjects(client);

function fromTask(task: TaskOut | null): Form {
  if (!task) return { title: '', description: '', priority: 'medium', due: '', assignee: null, project: null, tags: '' };
  return {
    title: task.title,
    description: task.description,
    priority: task.priority,
    due: task.due_date ?? '',
    assignee: null,
    project: task.project_id ? { id: task.project_id, label: task.project_name ?? '' } : null,
    tags: tagsText(task.tags),
  };
}

// Only opening (or another task) loads the form: a live change of the same task never resets it.
watch(
  [open, () => props.task?.id],
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromTask(props.task);
    original.value = fromTask(props.task);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

/** What this person changed since the form opened. */
function patch(task: TaskOut): TaskPatchIn {
  const f = form.value;
  const o = original.value;
  const out: TaskPatchIn = { id: task.id };
  if (f.title.trim() !== o.title.trim()) out.title = f.title.trim();
  if (f.description.trim() !== o.description.trim()) out.description = f.description.trim();
  if (f.priority !== o.priority) out.priority = f.priority;
  if (f.due !== o.due) out.due_date = f.due || null;
  if ((f.project?.id ?? null) !== (o.project?.id ?? null)) out.project_id = f.project?.id ?? null;
  const tags = parseTags(f.tags);
  if (tags.join('\n') !== parseTags(o.tags).join('\n')) out.tags = tags;
  return out;
}

async function save(): Promise<void> {
  const f = form.value;
  try {
    if (props.task) await update.run(patch(props.task));
    else
      await creation.run({
        title: f.title.trim(),
        description: f.description.trim(),
        priority: f.priority,
        due_date: f.due || null,
        assigned_to_id: f.assignee?.id ?? null,
        project_id: f.project?.id ?? null,
        tags: parseTags(f.tags),
      });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="task-form"
    :title="title"
    :submit-label="task ? $t('task.form.save') : $t('task.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.title.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="task-form">
        <ion-input
          data-testid="task-form-title"
          :value="form.title"
          :label="$t('task.form.title')"
          :placeholder="$t('task.form.titlePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.title"
          :class="invalid(fieldErrors.title)"
          @ion-input="form = { ...form, title: text($event.detail.value) }"
        />
        <ion-textarea
          data-testid="task-form-description"
          :value="form.description"
          :label="$t('task.form.description')"
          label-placement="floating"
          fill="outline"
          mode="md"
          auto-grow
          :rows="2"
          :maxlength="5000"
          :error-text="fieldErrors.description"
          :class="invalid(fieldErrors.description)"
          @ion-input="form = { ...form, description: text($event.detail.value) }"
        />
        <ion-select
          data-testid="task-form-priority"
          :value="form.priority"
          :label="$t('task.form.priority')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.priority"
          @ion-change="form = { ...form, priority: $event.detail.value as TaskPriority }"
        >
          <ion-select-option
            v-for="priority in PRIORITIES"
            :key="priority"
            :value="priority"
          >
            {{ t(`task.priority.${priority}`) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          data-testid="task-form-due_date"
          type="date"
          :value="form.due"
          :label="$t('task.form.due')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.due_date"
          :class="invalid(fieldErrors.due_date)"
          @ion-input="form = { ...form, due: text($event.detail.value) }"
        />
        <Combo
          v-if="!task"
          testid="task-form-assignee"
          :model-value="form.assignee"
          :search="findMembers"
          :label="$t('task.form.assignee')"
          :placeholder="$t('task.form.noAssignee')"
          :error-text="fieldErrors.assigned_to_id"
          @update:model-value="form = { ...form, assignee: $event }"
        />
        <Combo
          testid="task-form-project"
          :model-value="form.project"
          :search="findProjects"
          :label="$t('task.form.project')"
          :placeholder="$t('task.form.noProject')"
          :error-text="fieldErrors.project_id"
          @update:model-value="form = { ...form, project: $event }"
        />
        <ion-input
          data-testid="task-form-tags"
          :value="form.tags"
          :label="$t('task.form.tags')"
          :helper-text="$t('task.form.tagsHelper')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.tags"
          :class="invalid(fieldErrors.tags)"
          @ion-input="form = { ...form, tags: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.task-form {
  display: grid;
  gap: 14px;
}
</style>
