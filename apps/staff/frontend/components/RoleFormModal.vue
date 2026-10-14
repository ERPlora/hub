<script setup lang="ts">
// STAFF-F04 «Crear, editar y retirar un rol»: «New» asks for the old panel's Role name, Description and
// Color; «Edit · {name}» adds Order and Active (off retires the role: no longer offered in the records,
// which keep it). New sends `staff.role.create`; Edit only what changed with `staff.role.update`. The
// server judges (a name already taken is its 409); its refusals stay in the dialog.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonText, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { RoleIn, RoleOut, RolePatchIn } from '../operations';

const props = defineProps<{
  /** The role being edited; `null` = «New». */
  role: RoleOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface RoleForm {
  name: string;
  description: string;
  color: string;
  order: string;
  is_active: boolean;
}

const t = useT();
const form = ref<RoleForm>({ name: '', description: '', color: '', order: '0', is_active: true });
const creation = useCommand('staff.role.create');
const update = useCommand('staff.role.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.role ? update.error.value : creation.error.value));
const title = computed(() => (props.role ? t('staff.roles.form.titleEdit', { name: props.role.name }) : t('staff.roles.form.titleNew')));

function fromRole(role: RoleOut | null): RoleForm {
  return role
    ? { name: role.name, description: role.description, color: role.color, order: String(role.order), is_active: role.is_active }
    : { name: '', description: '', color: '', order: '0', is_active: true };
}

watch(
  () => [open.value, props.role?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromRole(props.role);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function patch(role: RoleOut): RolePatchIn {
  const f = form.value;
  const out: RolePatchIn = { id: role.id };
  if (f.name.trim() !== role.name) out.name = f.name.trim();
  if (f.description.trim() !== role.description) out.description = f.description.trim();
  if (f.color.trim() !== role.color) out.color = f.color.trim();
  if (f.order.trim() !== String(role.order)) out.order = whole(f.order);
  if (f.is_active !== role.is_active) out.is_active = f.is_active;
  return out;
}

async function save(): Promise<void> {
  const f = form.value;
  try {
    if (props.role) await update.run(patch(props.role));
    else await creation.run({ name: f.name.trim(), description: f.description.trim(), color: f.color.trim() } satisfies RoleIn);
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-role-form"
    :title="title"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="staff-role-form">
        <ion-input
          data-testid="staff-role-form-name"
          :value="form.name"
          :label="$t('staff.roles.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-input
          data-testid="staff-role-form-description"
          :value="form.description"
          :label="$t('staff.roles.form.description')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="500"
          :error-text="fieldErrors.description"
          :class="invalid(fieldErrors.description)"
          @ion-input="form = { ...form, description: text($event.detail.value) }"
        />
        <ion-input
          data-testid="staff-role-form-color"
          :value="form.color"
          :label="$t('staff.roles.form.color')"
          :placeholder="$t('staff.roles.form.colorPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="7"
          :error-text="fieldErrors.color"
          :class="invalid(fieldErrors.color)"
          @ion-input="form = { ...form, color: text($event.detail.value) }"
        >
          <ion-text
            v-if="/^#[0-9a-fA-F]{6}$/.test(form.color)"
            slot="end"
            aria-hidden="true"
          >
            <span
              class="staff-role-form__swatch"
              :style="{ background: form.color }"
            />
          </ion-text>
        </ion-input>
        <template v-if="role">
          <ion-input
            data-testid="staff-role-form-order"
            type="number"
            inputmode="numeric"
            min="0"
            :value="form.order"
            :label="$t('staff.roles.form.order')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.order"
            :class="invalid(fieldErrors.order)"
            @ion-input="form = { ...form, order: text($event.detail.value) }"
          />
          <ion-toggle
            data-testid="staff-role-form-is_active"
            label-placement="end"
            justify="start"
            :checked="form.is_active"
            @ion-change="form = { ...form, is_active: $event.detail.checked }"
          >
            {{ $t('staff.roles.form.active') }}
          </ion-toggle>
          <p
            class="staff-role-form__hint"
            data-testid="staff-role-form-active-hint"
          >
            {{ $t('staff.roles.form.activeHint') }}
          </p>
        </template>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-role-form {
  display: grid;
  gap: 14px;
}
.staff-role-form__hint {
  margin: -0.35rem 0 0;
  font-size: 0.8rem;
  line-height: 1.35;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.staff-role-form__swatch {
  display: block;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 50%;
  border: 1px solid var(--ion-border-color, #e5e3dd);
}
</style>
