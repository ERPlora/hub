<script setup lang="ts">
// TASK-F12 «Crear un proyecto»: «New project» asks for the old panel's Code («Code (q3-audit)», unique),
// Name and Color («Color (optional)», #RRGGBB). Refusals stay in the dialog, under their field.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { ref, watch } from 'vue';

const open = defineModel<boolean>('open', { default: false });

const creation = useCommand('task.project.create');
const form = ref({ code: '', name: '', color: '' });

watch(open, (isOpen) => {
  if (!isOpen) return;
  form.value = { code: '', name: '', color: '' };
  creation.error.value = null;
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  const f = form.value;
  try {
    await creation.run({ code: f.code.trim(), name: f.name.trim(), color: f.color.trim() });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="task-project-form"
    :title="$t('task.projects.form.titleNew')"
    :submit-label="$t('task.projects.form.create')"
    :pending="creation.pending.value"
    :error="creation.error.value"
    :submit-disabled="!form.code.trim() || !form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="task-project-form">
        <ion-input
          data-testid="task-project-form-code"
          :value="form.code"
          :label="$t('task.projects.form.code')"
          :placeholder="$t('task.projects.form.codePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="40"
          :error-text="fieldErrors.code"
          :class="invalid(fieldErrors.code)"
          @ion-input="form = { ...form, code: text($event.detail.value) }"
        />
        <ion-input
          data-testid="task-project-form-name"
          :value="form.name"
          :label="$t('task.projects.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-input
          data-testid="task-project-form-color"
          :value="form.color"
          :label="$t('task.projects.form.color')"
          :placeholder="$t('task.projects.form.colorPlaceholder')"
          :helper-text="$t('task.projects.form.colorHelper')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="7"
          :error-text="fieldErrors.color"
          :class="invalid(fieldErrors.color)"
          @ion-input="form = { ...form, color: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.task-project-form {
  display: grid;
  gap: 14px;
}
</style>
