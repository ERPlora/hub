<script lang="ts">
import type { InputOf } from '@erplora/ui/sdk';

/** What the form edits: the three fields of an item. */
export type ItemFields = Required<InputOf<'demo.item.create'>>;

/** The fields of `now` that differ from `from`: an edit sends only these (DEMO-F02). */
export function changedFields(from: ItemFields, now: ItemFields): Partial<ItemFields> {
  return Object.fromEntries(Object.entries(now).filter(([key, value]) => from[key as keyof ItemFields] !== value));
}
</script>

<script setup lang="ts">
// The item's form (DEMO-F01/F02), shared by the «New item» and «Edit item» pages: name, status and
// note. The server validates: a 422 paints each message under its field; any other failure shows
// its message in a banner. The page owns the model (`v-model`) and runs the command on `submit`.
import { InlineFeedback } from '@erplora/ui/components';
import { type ApiError, fieldErrors } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed } from 'vue';

const form = defineModel<ItemFields>({ required: true });
const props = defineProps<{ error: ApiError | null; pending: boolean }>();
const emit = defineEmits<{ submit: [] }>();

const errors = computed(() => fieldErrors(props.error));
/** A failure that belongs to no field (permission, network…). */
const failure = computed(() => (props.error && Object.keys(errors.value).length === 0 ? props.error.message : ''));
const invalid = (field: keyof ItemFields) => ({ 'ion-invalid': !!errors.value[field], 'ion-touched': !!errors.value[field] });

/** A new model per change: the parent's object is never mutated. */
function set<K extends keyof ItemFields>(field: K, value: unknown): void {
  form.value = { ...form.value, [field]: value ?? '' };
}
</script>

<template>
  <form
    class="demo-form"
    data-testid="demo-form"
    novalidate
    @submit.prevent="emit('submit')"
  >
    <InlineFeedback
      v-if="failure"
      tone="danger"
      data-testid="demo-form-failure"
    >
      {{ failure }}
    </InlineFeedback>
    <ion-input
      data-testid="demo-form-name"
      :model-value="form.name"
      :label="$t('demo.form.name')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="120"
      :error-text="errors.name"
      :class="invalid('name')"
      @update:model-value="set('name', $event)"
    />
    <ion-select
      data-testid="demo-form-status"
      :model-value="form.status"
      :label="$t('demo.form.status')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :error-text="errors.status"
      :class="invalid('status')"
      @update:model-value="set('status', $event)"
    >
      <ion-select-option value="open">
        {{ $t('demo.status.open') }}
      </ion-select-option>
      <ion-select-option value="done">
        {{ $t('demo.status.done') }}
      </ion-select-option>
    </ion-select>
    <ion-textarea
      data-testid="demo-form-note"
      :model-value="form.note"
      :label="$t('demo.form.note')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :auto-grow="true"
      :error-text="errors.note"
      :class="invalid('note')"
      @update:model-value="set('note', $event)"
    />
    <ion-button
      type="submit"
      expand="block"
      data-testid="demo-form-save"
      :disabled="pending"
    >
      {{ $t('demo.form.save') }}
    </ion-button>
  </form>
</template>

<style scoped>
.demo-form {
  display: grid;
  gap: 16px;
}
</style>
