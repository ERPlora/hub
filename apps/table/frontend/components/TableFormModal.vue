<script setup lang="ts">
// «Edit table» and «New table» (WORKBOOK «Plano de sala», «Mesas»; TABLE-F02, F04, F05).
// - Edit: Number, Capacity, Name (optional), Shape, Status — Available or Blocked: occupied and reserved
//   are the room's, not a person's —, Zone and In use; «Save» sends only what changed
//   (`table.table.update`; another zone is `move_to_zone_id`); «Delete» (whoever may) asks first.
// - New: Number (empty = the first free number of the zone), Capacity and Zone (`table.table.create`;
//   the server puts it on the first free spot of the plan).
// A number is required when editing; refusals (a number taken, a table with an open check) stay here.
import { ConfirmDialog, FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { TableOut, TablePatchIn, TableShape, ZoneOut } from '../operations';

const props = withDefaults(
  defineProps<{
    /** The table being edited; `null` = «New table». */
    table: TableOut | null;
    zones: ZoneOut[];
    /** The zone a new table goes to by default. */
    defaultZoneId?: string | null;
    canDelete?: boolean;
  }>(),
  { defaultZoneId: null, canDelete: false },
);

const open = defineModel<boolean>('open', { default: false });

const SHAPES: readonly TableShape[] = ['square', 'round', 'rectangle'];
const NO_ZONE = '';

interface Form {
  number: string;
  capacity: string;
  name: string;
  shape: TableShape;
  status: 'available' | 'blocked';
  zone: string;
  active: boolean;
}

const t = useT();
const creation = useCommand('table.table.create');
const update = useCommand('table.table.update');
const removal = useCommand('table.table.delete');
const pending = computed(() => creation.pending.value || update.pending.value || removal.pending.value);
const error = computed(() => (props.table ? update.error.value : creation.error.value));
const editing = computed(() => props.table !== null);
const confirmDelete = ref(false);

function fromTable(table: TableOut | null): Form {
  if (!table) {
    return { number: '', capacity: '4', name: '', shape: 'square', status: 'available', zone: props.defaultZoneId ?? props.zones[0]?.id ?? NO_ZONE, active: true };
  }
  return {
    number: table.number,
    capacity: String(table.capacity),
    name: table.name,
    shape: table.shape,
    status: table.blocked ? 'blocked' : 'available',
    zone: table.zone_id ?? NO_ZONE,
    active: table.is_active,
  };
}

const form = ref<Form>(fromTable(props.table));
// Two sources, compared one by one: a live repaint of the same table (a new row, same id) keeps what is
// being typed; opening the dialog or another table starts over.
watch(
  [open, () => props.table?.id],
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromTable(props.table);
    creation.error.value = null;
    update.error.value = null;
    removal.error.value = null;
  },
  { immediate: true },
);

const numberMissing = computed(() => editing.value && !form.value.number.trim());
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  form.value = { ...form.value, [field]: value };
}

function patch(table: TableOut): TablePatchIn {
  const f = form.value;
  const out: TablePatchIn = { id: table.id };
  if (f.number.trim() !== table.number) out.number = f.number.trim();
  if (f.name.trim() !== table.name) out.name = f.name.trim();
  if (f.capacity.trim() !== String(table.capacity)) out.capacity = whole(f.capacity);
  if (f.shape !== table.shape) out.shape = f.shape;
  if ((f.status === 'blocked') !== table.blocked) out.blocked = f.status === 'blocked';
  if ((f.zone || null) !== table.zone_id) out.move_to_zone_id = f.zone || null;
  if (f.active !== table.is_active) out.is_active = f.active;
  return out;
}

async function save(): Promise<void> {
  if (numberMissing.value || pending.value) return;
  const f = form.value;
  try {
    if (props.table) await update.run(patch(props.table));
    else {
      await creation.run({
        zone_id: f.zone || null,
        ...(f.number.trim() ? { number: f.number.trim() } : {}),
        capacity: whole(f.capacity || '4'),
      });
    }
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}

async function remove(): Promise<void> {
  if (!props.table) return;
  try {
    await removal.run({ id: props.table.id });
  } catch {
    return; // The confirmation says why.
  }
  confirmDelete.value = false;
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="table-form"
    :title="editing ? $t('table.form.titleEdit') : $t('table.form.titleNew')"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="table-form">
        <div class="table-form__pair">
          <ion-input
            data-testid="table-form-number"
            :value="form.number"
            :label="$t('table.form.number')"
            :placeholder="editing ? undefined : $t('table.add.numberPlaceholder')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="20"
            :error-text="fieldErrors.number"
            :class="invalid(fieldErrors.number)"
            @ion-input="set('number', text($event.detail.value))"
          />
          <ion-input
            data-testid="table-form-capacity"
            type="number"
            inputmode="numeric"
            min="1"
            :value="form.capacity"
            :label="$t('table.form.capacity')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.capacity"
            :class="invalid(fieldErrors.capacity)"
            @ion-input="set('capacity', text($event.detail.value))"
          />
        </div>
        <p
          v-if="numberMissing"
          class="table-form__hint"
          data-testid="table-form-number-required"
        >
          {{ $t('table.form.numberRequired') }}
        </p>
        <ion-input
          v-if="editing"
          data-testid="table-form-name"
          :value="form.name"
          :label="$t('table.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="set('name', text($event.detail.value))"
        />
        <div
          v-if="editing"
          class="table-form__pair"
        >
          <ion-select
            data-testid="table-form-shape"
            :value="form.shape"
            :label="$t('table.form.shape')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="set('shape', $event.detail.value)"
          >
            <ion-select-option
              v-for="shape in SHAPES"
              :key="shape"
              :value="shape"
            >
              {{ t(`table.shape.${shape}`) }}
            </ion-select-option>
          </ion-select>
          <ion-select
            data-testid="table-form-status"
            :value="form.status"
            :label="$t('table.form.status')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="set('status', $event.detail.value)"
          >
            <ion-select-option value="available">
              {{ $t('table.status.available') }}
            </ion-select-option>
            <ion-select-option value="blocked">
              {{ $t('table.status.blocked') }}
            </ion-select-option>
          </ion-select>
        </div>
        <ion-select
          data-testid="table-form-zone"
          :value="form.zone"
          :label="$t('table.form.zone')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('zone', $event.detail.value ?? '')"
        >
          <ion-select-option :value="NO_ZONE">
            {{ $t('table.form.noZone') }}
          </ion-select-option>
          <ion-select-option
            v-for="zone in zones"
            :key="zone.id"
            :value="zone.id"
          >
            {{ zone.name }}
          </ion-select-option>
        </ion-select>
        <ion-toggle
          v-if="editing"
          data-testid="table-form-active"
          label-placement="end"
          justify="start"
          :checked="form.active"
          @ion-change="set('active', $event.detail.checked)"
        >
          {{ $t('table.form.active') }}
        </ion-toggle>
      </div>
    </template>
    <template #footer="{ cancel, submit }">
      <ion-button
        v-if="editing && canDelete"
        class="table-form__delete"
        fill="outline"
        color="danger"
        data-testid="table-form-delete"
        :disabled="pending"
        @click="confirmDelete = true"
      >
        {{ $t('table.form.delete') }}
      </ion-button>
      <ion-button
        fill="clear"
        data-testid="table-form-cancel"
        :disabled="pending"
        @click="cancel"
      >
        {{ $t('table.cancel') }}
      </ion-button>
      <ion-button
        data-testid="table-form-submit"
        :disabled="pending || numberMissing"
        @click="submit"
      >
        {{ editing ? $t('table.form.save') : $t('table.form.create') }}
      </ion-button>
    </template>
  </FormModal>
  <ConfirmDialog
    v-if="table"
    v-model:open="confirmDelete"
    testid="table-form-delete-confirm"
    tone="danger"
    :title="t('table.form.deleteTitle', { number: table.number })"
    :message="t('table.form.deleteMessage')"
    :confirm-label="t('table.form.deleteConfirm')"
    :cancel-label="t('table.cancel')"
    :pending="removal.pending.value"
    :error="removal.error.value"
    @confirm="remove"
    @cancel="confirmDelete = false"
  />
</template>

<style scoped>
.table-form {
  display: grid;
  gap: 14px;
}
.table-form__pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.table-form__hint {
  margin: -6px 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger, #c5000f);
}
.table-form__delete {
  margin-inline-end: auto;
}
</style>
