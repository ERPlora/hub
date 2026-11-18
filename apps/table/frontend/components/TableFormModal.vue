<script setup lang="ts">
// «Edit table» and «New table» (WORKBOOK «Plano de sala», «Mesas»; TABLE-F02, F04, F05).
// - Edit: Number, Capacity, Width and Height of its box on the plan, Name (optional), Shape, Status —
//   Available or Blocked: occupied and reserved are the room's, not a person's —, Zone and In use; «Save»
//   sends only what changed (`table.table.update`; another zone is `move_to_zone_id`; a new size is
//   `table.table.move` where the box already is, first, so a refused size saves nothing); «Delete»
//   (whoever may) asks first.
// - New: Number (empty = the first free number of the zone), Capacity, Width and Height (empty = the
//   standard box) and Zone (`table.table.create`; the server puts it on the first free spot of the plan).
// A number is required when editing; refusals (a number taken, a table with an open check) stay here.
import { ConfirmDialog, FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';

import { useT } from '../composables/useT';
import type { TableMoveIn, TableOut, TablePatchIn, TableShape, ZoneOut } from '../operations';

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

const canDismiss = useUnsavedFormOnOpen('table-form', () => form.value, open);

const SHAPES: readonly TableShape[] = ['square', 'round', 'rectangle'];
const NO_ZONE = '';
/** The sides of a box the server takes, in pixels of the plan (`MIN_BOX` and `MAX_PLAN` of the table model). */
const SIDE = { min: 24, max: 10_000 } as const;
const SIDES = ['width', 'height'] as const;

type Size = Pick<TableMoveIn, 'width' | 'height'>;

interface Form {
  number: string;
  capacity: string;
  width: string;
  height: string;
  name: string;
  shape: TableShape;
  status: 'available' | 'blocked';
  zone: string;
  active: boolean;
}

const t = useT();
const creation = useCommand('table.table.create');
const update = useCommand('table.table.update');
const resize = useCommand('table.table.move');
const removal = useCommand('table.table.delete');
const pending = computed(() => creation.pending.value || update.pending.value || resize.pending.value || removal.pending.value);
const error = computed(() => (props.table ? (resize.error.value ?? update.error.value) : creation.error.value));
const editing = computed(() => props.table !== null);
const confirmDelete = ref(false);

function fromTable(table: TableOut | null): Form {
  if (!table) {
    const zone = props.defaultZoneId ?? props.zones[0]?.id ?? NO_ZONE;
    return { number: '', capacity: '4', width: '', height: '', name: '', shape: 'square', status: 'available', zone, active: true };
  }
  return {
    number: table.number,
    capacity: String(table.capacity),
    width: String(table.width),
    height: String(table.height),
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
    resize.error.value = null;
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

/** The sides typed, as the server takes them. An empty side is left out (the standard box for a new table, the
 *  side it has for one being edited), and so is a side of `table` that stays as it is. */
function typedSize(table: TableOut | null = null): Size {
  const size: Size = {};
  for (const side of SIDES) {
    const typed = form.value[side].trim();
    if (typed && whole(typed) !== table?.[side]) size[side] = whole(typed);
  }
  return size;
}

async function saveEdit(table: TableOut): Promise<void> {
  resize.error.value = null;
  const size = typedSize(table);
  const changes = patch(table);
  const resized = Object.keys(size).length > 0;
  if (resized) await resize.run({ id: table.id, position_x: table.position_x, position_y: table.position_y, ...size });
  if (!resized || Object.keys(changes).length > 1) await update.run(changes);
}

async function saveNew(): Promise<void> {
  const f = form.value;
  await creation.run({
    zone_id: f.zone || null,
    ...(f.number.trim() ? { number: f.number.trim() } : {}),
    capacity: whole(f.capacity || '4'),
    ...typedSize(),
  });
}

async function save(): Promise<void> {
  if (numberMissing.value || pending.value) return;
  try {
    await (props.table ? saveEdit(props.table) : saveNew());
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
    :can-dismiss="canDismiss"
    testid="table-form"
    :title="editing ? $t('table.form.titleEdit') : $t('table.form.titleNew')"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div
        class="table-form"
      >
        <div class="table-form__pair">
          <ion-input
            data-testid="table-form-number"
            name="number"
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
            name="capacity"
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
        <div class="table-form__pair">
          <ion-input
            v-for="side in SIDES"
            :key="side"
            :data-testid="`table-form-${side}`"
            :name="side"
            type="number"
            inputmode="numeric"
            :min="SIDE.min"
            :max="SIDE.max"
            :value="form[side]"
            :label="t(`table.form.${side}`)"
            :placeholder="editing ? undefined : $t('table.form.sizePlaceholder')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors[side]"
            :class="invalid(fieldErrors[side])"
            @ion-input="set(side, text($event.detail.value))"
          />
        </div>
        <ion-input
          v-if="editing"
          data-testid="table-form-name"
          name="name"
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
