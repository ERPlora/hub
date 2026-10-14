<script setup lang="ts">
// SALE-F36: «New quick note» (the «+» of Quick notes) or «Edit quick note» (a row's «Edit»), as the old
// table's create panel: Note (up to 80 characters) and Position, «Add» or «Save». An edit sends only
// what changed (nothing changed: it just closes). It closes once the server saved it — the live list
// paints the note —; a refusal keeps it open with what was typed (`refusal`).
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../../composables/useT';
import type { QuickNoteOut } from '../../operations';
import { refusal } from './refusal';

const props = defineProps<{
  /** The note to edit; `null` adds a new one. */
  note: QuickNoteOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const create = useCommand('sale.quick_note.create');
const update = useCommand('sale.quick_note.update');

const text = ref('');
const order = ref('0');

const editing = computed(() => props.note !== null);
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => refusal(create.error.value ?? update.error.value, t('sale.quickNotes.saveFailed')));
const complete = computed(() => text.value.trim() !== '');
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

// Every opening starts from the note being edited (or blank) and with no refusal left over.
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    text.value = props.note?.text ?? '';
    order.value = String(props.note?.sort_order ?? 0);
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

/** The Position as the server takes it: blank is its first place, 0. */
const position = (): number => (order.value.trim() === '' ? 0 : Number(order.value));

async function save(): Promise<void> {
  const note = props.note;
  const fields = { text: text.value.trim(), sort_order: position() };
  try {
    if (!note) {
      await create.run(fields);
    } else {
      const changed = {
        ...(fields.text !== note.text ? { text: fields.text } : {}),
        ...(fields.sort_order !== note.sort_order ? { sort_order: fields.sort_order } : {}),
      };
      if (Object.keys(changed).length) await update.run({ id: note.id, ...changed });
    }
  } catch {
    return; // The dialog paints the refusal.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="sale-quick-note-form"
    :title="editing ? $t('sale.quickNotes.form.editTitle') : $t('sale.quickNotes.form.createTitle')"
    :submit-label="editing ? $t('sale.quickNotes.form.save') : $t('sale.quickNotes.form.add')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="sale-backoffice-form">
        <ion-input
          data-testid="sale-quick-note-form-text"
          :value="text"
          :label="$t('sale.quickNotes.columns.text')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="80"
          :error-text="fieldErrors.text"
          :class="invalid(fieldErrors.text)"
          @ion-input="text = String($event.detail.value ?? '')"
        />
        <ion-input
          data-testid="sale-quick-note-form-order"
          :value="order"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :label="$t('sale.quickNotes.columns.sortOrder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="order = String($event.detail.value ?? '')"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.sale-backoffice-form {
  display: grid;
  gap: 14px;
}
</style>
