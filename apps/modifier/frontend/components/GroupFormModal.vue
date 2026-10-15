<script setup lang="ts">
// MODIFIER-F02 «Crear un grupo» and F03 «Cambiar un grupo»: «New group» asks for the old screen's Name,
// «Kitchen ticket name», «Minimum (1 or more = required)» and «Maximum (0 = no ceiling)», plus whether
// an option can repeat and the Order; Edit opens «Editing group — {name}» and sends only what changed
// with `modifier.group.update`. The rules (a maximum below the minimum, a taken name) are the server's:
// its refusal stays in the dialog, under its field, and what was typed stays.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { GroupIn, GroupOut, GroupPatchIn } from '../operations';

const props = defineProps<{
  /** The group being edited; `null` = «New group». */
  group: GroupOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  kitchenName: string;
  min: string;
  max: string;
  repeat: boolean;
  order: string;
}

const EMPTY: Form = { name: '', kitchenName: '', min: '0', max: '0', repeat: false, order: '0' };

const t = useT();
const creation = useCommand('modifier.group.create');
const update = useCommand('modifier.group.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.group ? update.error.value : creation.error.value));
const title = computed(() => (props.group ? t('modifier.groups.form.titleEdit', { name: props.group.name }) : t('modifier.groups.form.titleNew')));
const form = ref<Form>({ ...EMPTY });

function fromGroup(group: GroupOut | null): Form {
  if (!group) return { ...EMPTY };
  return {
    name: group.name,
    kitchenName: group.kitchen_name,
    min: String(group.min_choices),
    max: String(group.max_choices),
    repeat: group.allow_repeat,
    order: String(group.sort_order),
  };
}

watch(
  () => [open.value, props.group?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromGroup(props.group);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function fields(): Required<GroupIn> {
  const f = form.value;
  return {
    name: f.name.trim(),
    kitchen_name: f.kitchenName.trim(),
    min_choices: whole(f.min || '0'),
    max_choices: whole(f.max || '0'),
    allow_repeat: f.repeat,
    sort_order: whole(f.order || '0'),
  };
}

function patch(group: GroupOut): GroupPatchIn {
  const out: GroupPatchIn = { id: group.id };
  const now = fields();
  const before: Required<GroupIn> = {
    name: group.name,
    kitchen_name: group.kitchen_name,
    min_choices: group.min_choices,
    max_choices: group.max_choices,
    allow_repeat: group.allow_repeat,
    sort_order: group.sort_order,
  };
  for (const key of Object.keys(now) as Array<keyof GroupIn>) {
    if (now[key] !== before[key]) (out as Record<string, unknown>)[key] = now[key];
  }
  return out;
}

async function save(): Promise<void> {
  try {
    if (props.group) await update.run(patch(props.group));
    else await creation.run(fields());
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="modifier-group-form"
    :title="title"
    :submit-label="group ? $t('modifier.groups.form.save') : $t('modifier.groups.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="modifier-form">
        <ion-input
          data-testid="modifier-group-form-name"
          :value="form.name"
          :label="$t('modifier.groups.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-input
          data-testid="modifier-group-form-kitchen_name"
          :value="form.kitchenName"
          :label="$t('modifier.groups.form.kitchenName')"
          :helper-text="$t('modifier.groups.form.kitchenHint')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.kitchen_name"
          :class="invalid(fieldErrors.kitchen_name)"
          @ion-input="form = { ...form, kitchenName: text($event.detail.value) }"
        />
        <div class="modifier-form__pair">
          <ion-input
            data-testid="modifier-group-form-min_choices"
            type="number"
            inputmode="numeric"
            min="0"
            max="50"
            :value="form.min"
            :label="$t('modifier.groups.form.min')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.min_choices"
            :class="invalid(fieldErrors.min_choices)"
            @ion-input="form = { ...form, min: text($event.detail.value) }"
          />
          <ion-input
            data-testid="modifier-group-form-max_choices"
            type="number"
            inputmode="numeric"
            min="0"
            max="50"
            :value="form.max"
            :label="$t('modifier.groups.form.max')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.max_choices"
            :class="invalid(fieldErrors.max_choices)"
            @ion-input="form = { ...form, max: text($event.detail.value) }"
          />
        </div>
        <ion-toggle
          data-testid="modifier-group-form-allow_repeat"
          :checked="form.repeat"
          label-placement="end"
          justify="start"
          @ion-change="form = { ...form, repeat: $event.detail.checked }"
        >
          {{ $t('modifier.groups.form.repeat') }}
        </ion-toggle>
        <ion-input
          data-testid="modifier-group-form-sort_order"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form.order"
          :label="$t('modifier.groups.form.order')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="form = { ...form, order: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.modifier-form {
  display: grid;
  gap: 14px;
}
.modifier-form__pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}
</style>
