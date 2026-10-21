<script setup lang="ts">
// A course in the menu's builder (WORKBOOK «Constructor del menú»; COMBO-F05, F06, F12): its name and
// the rule the till applies, and with the right to manage the handle, «Move up», «Move down», «Edit
// details» and «Withdraw» (emitted: the page owns the courses' order and form). Inside, «Choices», one
// row per product with its supplement and why it is not offered (sold out here, or deactivated or
// deleted in Inventory); per row the handle, up and down (the whole order saved at once), «Sold out» /
// «Available», edit (keeps its place) and remove (after its confirmation). Below, the product picker,
// «Supplement» (it may be negative), «Add choice» and «Add several». A refusal is said in the course.
import { Combo, type ComboOption, ConfirmDialog, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonReorder, IonReorderGroup } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDelta } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchProducts } from '../lib/pickers';
import { courseRule } from '../lib/rules';
import type { GroupOut, OptionOut, OptionPatchIn, OptionStatus } from '../operations';
import BulkAddModal from './BulkAddModal.vue';
import MoneyInput from './MoneyInput.vue';

/** Sold out, here or in Inventory (INVENTORY-F29): it comes back, a warning; the rest needs fixing. */
const SOLD_OUT: ReadonlySet<OptionStatus> = new Set(['sold_out', 'product_sold_out']);

const props = defineProps<{
  course: GroupOut;
  /** Its place among the menu's courses, and how many there are (for up and down). */
  index: number;
  count: number;
}>();
const emit = defineEmits<{ move: [delta: -1 | 1]; edit: []; remove: [] }>();

const session = useSession();
const canManage = computed(() => session.can('combo.manage'));
const t = useT();
const locale = useLocale();
const client = useLiveClient();
const searchArticles = computed(() => searchProducts(client, locale.value));

const create = useCommand('combo.option.create');
const update = useCommand('combo.option.update');
const reorder = useCommand('combo.option.reorder');
const remove = useCommand('combo.option.delete');

const options = computed(() => props.course.options);
const rule = computed(() => courseRule(props.course, t));
const prefix = computed(() => `combo-course-${props.course.id}`);

// --- The order (handle and arrows end in the same write) -------------------------------------

function moved<T>(list: readonly T[], from: number, to: number): T[] {
  const out = [...list];
  const [row] = out.splice(from, 1);
  out.splice(to, 0, row);
  return out;
}

async function saveOrder(ids: string[]): Promise<void> {
  try {
    await reorder.run({ group_id: props.course.id, option_ids: ids });
  } catch {
    // Said in the course; the live course comes back with what the server holds.
  }
}

function step(choice: OptionOut, delta: -1 | 1): void {
  const from = options.value.findIndex((o) => o.id === choice.id);
  const to = from + delta;
  if (from < 0 || to < 0 || to >= options.value.length) return;
  void saveOrder(moved(options.value, from, to).map((o) => o.id));
}

function onReorder(event: CustomEvent<{ from: number; to: number; complete: (data?: boolean | unknown[]) => unknown }>): void {
  const { from, to } = event.detail;
  // Ionic puts the row back; the live course paints the order the server saved.
  event.detail.complete(false);
  if (from !== to) void saveOrder(moved(options.value, from, to).map((o) => o.id));
}

// --- Sold out / available, and remove ----------------------------------------------------------

async function toggle(choice: OptionOut): Promise<void> {
  try {
    await update.run({ id: choice.id, is_available: !choice.is_available });
  } catch {
    // Said in the course.
  }
}

const removing = ref<OptionOut | null>(null);
const removeOpen = ref(false);

function askRemove(choice: OptionOut): void {
  remove.error.value = null;
  removing.value = choice;
  removeOpen.value = true;
}

async function confirmRemove(): Promise<void> {
  if (!removing.value) return;
  try {
    await remove.run({ id: removing.value.id });
  } catch {
    return; // The dialog says why.
  }
  if (editing.value?.id === removing.value.id) resetForm();
  removeOpen.value = false;
}

// --- The choice form ---------------------------------------------------------------------------

const editing = ref<OptionOut | null>(null);
const article = ref<ComboOption | null>(null);
const delta = ref('');
const tried = ref(false);
const reason = ref('');
const bulkOpen = ref(false);

function resetForm(): void {
  editing.value = null;
  article.value = null;
  delta.value = '';
  tried.value = false;
  reason.value = '';
  create.error.value = null;
  update.error.value = null;
}

function startEdit(choice: OptionOut): void {
  resetForm();
  editing.value = choice;
  article.value = { id: choice.product_id, label: choice.product_name };
  delta.value = choice.price_delta ? moneyFieldText(choice.price_delta, locale.value) : '';
}

/** The refusal of the last save: of the form when it was one, of anything else in the course otherwise. */
const formError = computed<ApiError | null>(() => (editing.value ? update.error.value : create.error.value));
const fields = computed(() => formError.value?.fields ?? {});
const articleError = computed(() => fields.value.product_id || fields.value.new_product_id || fields.value.product || undefined);
const courseError = computed(() => {
  const errors = [reorder.error.value, remove.error.value && !removeOpen.value ? remove.error.value : null, formError.value, update.error.value];
  const shown = errors.find((error) => error && !Object.keys(error.fields ?? {}).length);
  return shown?.message;
});

async function save(): Promise<void> {
  tried.value = true;
  reason.value = '';
  if (!article.value) {
    reason.value = t('combo.choices.noProduct');
    return;
  }
  const picked = article.value.id;
  if (options.value.some((o) => o.product_id === picked && o.id !== editing.value?.id)) {
    reason.value = t('combo.choices.duplicate');
    return;
  }
  const read = parseMoney(delta.value, { signed: true });
  if (!read.ok) return;
  const price = read.cents ?? 0;
  try {
    if (editing.value) {
      const change: OptionPatchIn = { id: editing.value.id };
      if (picked !== editing.value.product_id) change.new_product_id = picked;
      if (price !== editing.value.price_delta) change.price_delta = price;
      if (Object.keys(change).length > 1) await update.run(change);
    } else {
      await create.run({ group_id: props.course.id, product_id: picked, price_delta: price });
    }
  } catch {
    return; // Said under its field or in the course; what was typed stays.
  }
  resetForm();
}
</script>

<template>
  <section
    class="combo-course"
    :data-testid="prefix"
    :data-required="String(course.min_choices >= 1)"
  >
    <div class="combo-course__head">
      <ion-reorder
        v-if="canManage"
        :data-testid="`${prefix}-drag`"
        :aria-label="t('combo.courses.drag')"
      />
      <span
        class="combo-course__name"
        :data-testid="`${prefix}-name`"
      >{{ course.name }}</span>
      <span
        class="combo-course__rule"
        :data-testid="`${prefix}-rule`"
      >{{ rule }}</span>
      <div
        v-if="canManage"
        class="combo-course__actions"
      >
        <ion-button
          fill="clear"
          size="small"
          :data-testid="`${prefix}-up`"
          :aria-label="t('combo.courses.moveUp')"
          :disabled="index === 0"
          @click="emit('move', -1)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:chevron-up-outline"
          />
        </ion-button>
        <ion-button
          fill="clear"
          size="small"
          :data-testid="`${prefix}-down`"
          :aria-label="t('combo.courses.moveDown')"
          :disabled="index === count - 1"
          @click="emit('move', 1)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:chevron-down-outline"
          />
        </ion-button>
        <ion-button
          fill="outline"
          size="small"
          :data-testid="`${prefix}-edit`"
          @click="emit('edit')"
        >
          {{ $t('combo.courses.edit') }}
        </ion-button>
        <ion-button
          fill="outline"
          size="small"
          color="danger"
          :data-testid="`${prefix}-delete`"
          @click="emit('remove')"
        >
          {{ $t('combo.courses.delete') }}
        </ion-button>
      </div>
    </div>

    <h3 class="combo-course__subtitle">
      {{ $t('combo.choices.title') }}
    </h3>
    <p
      v-if="options.length === 0"
      class="combo-course__muted"
      :data-testid="`${prefix}-empty`"
    >
      {{ $t('combo.choices.empty') }}
    </p>
    <div
      v-else
      class="combo-course__choices"
    >
      <ion-reorder-group
        :data-testid="`${prefix}-choices`"
        :disabled="!canManage"
        @ion-item-reorder="onReorder"
      >
        <div
          v-for="(choice, i) in options"
          :key="choice.id"
          class="combo-course__row"
          :data-testid="`combo-choice-${choice.id}`"
          :data-status="choice.status"
        >
          <ion-reorder
            v-if="canManage"
            :aria-label="t('combo.courses.drag')"
          />
          <span class="combo-course__choice">
            <span class="combo-course__choice-name">{{ choice.product_name }}</span>
            <span
              v-if="choice.price_delta"
              class="combo-course__delta"
            >{{ formatDelta(choice.price_delta, locale) }}</span>
            <StatusPill
              v-if="choice.status !== 'offered'"
              size="sm"
              :tone="SOLD_OUT.has(choice.status) ? 'warning' : 'danger'"
              :label="t(`combo.choices.status.${choice.status}`)"
              :data-testid="`combo-choice-${choice.id}-status`"
            />
          </span>
          <span
            v-if="canManage"
            class="combo-course__row-actions"
          >
            <ion-button
              fill="clear"
              size="small"
              :data-testid="`combo-choice-${choice.id}-up`"
              :aria-label="t('combo.courses.moveUp')"
              :disabled="i === 0"
              @click="step(choice, -1)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:chevron-up-outline"
              />
            </ion-button>
            <ion-button
              fill="clear"
              size="small"
              :data-testid="`combo-choice-${choice.id}-down`"
              :aria-label="t('combo.courses.moveDown')"
              :disabled="i === options.length - 1"
              @click="step(choice, 1)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:chevron-down-outline"
              />
            </ion-button>
            <ion-button
              fill="outline"
              size="small"
              :data-testid="`combo-choice-${choice.id}-availability`"
              @click="toggle(choice)"
            >
              {{ choice.is_available ? $t('combo.choices.markSoldOut') : $t('combo.choices.markAvailable') }}
            </ion-button>
            <ion-button
              fill="clear"
              size="small"
              :data-testid="`combo-choice-${choice.id}-edit`"
              :aria-label="t('combo.choices.edit')"
              @click="startEdit(choice)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:create-outline"
              />
            </ion-button>
            <ion-button
              fill="clear"
              size="small"
              color="danger"
              :data-testid="`combo-choice-${choice.id}-delete`"
              :aria-label="t('combo.choices.delete')"
              @click="askRemove(choice)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:trash-outline"
              />
            </ion-button>
          </span>
        </div>
      </ion-reorder-group>
    </div>

    <template v-if="canManage">
      <p
        v-if="editing"
        class="combo-course__editing"
        :data-testid="`${prefix}-editing`"
      >
        {{ $t('combo.choices.editing', { article: editing.product_name }) }}
      </p>
      <div class="combo-course__form">
        <Combo
          :testid="`${prefix}-picker`"
          :model-value="article"
          :search="searchArticles"
          :label="t('combo.choices.picker')"
          :placeholder="t('combo.choices.pickerPlaceholder')"
          :error-text="articleError"
          @update:model-value="article = $event"
        />
        <MoneyInput
          v-model="delta"
          signed
          :testid="`${prefix}-delta`"
          :label="t('combo.choices.delta')"
          :error-text="fields.price_delta"
          :show-error="tried"
        />
        <div class="combo-course__form-actions">
          <ion-button
            size="small"
            :data-testid="`${prefix}-save`"
            :disabled="create.pending.value || update.pending.value"
            @click="save"
          >
            {{ editing ? $t('combo.save') : $t('combo.choices.add') }}
          </ion-button>
          <ion-button
            v-if="editing"
            size="small"
            fill="outline"
            :data-testid="`${prefix}-cancel`"
            @click="resetForm"
          >
            {{ $t('combo.cancel') }}
          </ion-button>
          <ion-button
            v-else
            size="small"
            fill="outline"
            :data-testid="`${prefix}-bulk`"
            @click="bulkOpen = true"
          >
            <HubIcon
              slot="start"
              name="ion:add-outline"
            />
            {{ $t('combo.bulk.open') }}
          </ion-button>
        </div>
      </div>
      <p class="combo-course__muted">
        {{ $t('combo.choices.deltaHelp') }}
      </p>
      <p
        v-if="reason"
        class="combo-course__reason"
        :data-testid="`${prefix}-reason`"
      >
        {{ reason }}
      </p>
    </template>
    <InlineFeedback
      v-if="courseError"
      tone="danger"
      :data-testid="`${prefix}-error`"
    >
      {{ courseError }}
    </InlineFeedback>

    <BulkAddModal
      v-if="canManage"
      v-model:open="bulkOpen"
      :course="course"
    />
    <ConfirmDialog
      v-model:open="removeOpen"
      testid="combo-choice-delete"
      tone="danger"
      :title="t('combo.choices.deleteTitle')"
      :message="removing ? t('combo.choices.deleteMessage', { name: removing.product_name, course: course.name }) : ''"
      :confirm-label="t('combo.choices.deleteConfirm')"
      :cancel-label="t('combo.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmRemove"
      @cancel="removeOpen = false"
    />
  </section>
</template>

<style scoped>
.combo-course {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  background: var(--ion-color-step-50, rgba(24, 24, 27, 0.04));
  display: grid;
  gap: 0.5rem;
}
.combo-course__head {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.combo-course__name {
  font-weight: 600;
  flex: 1 1 auto;
  overflow-wrap: anywhere;
}
.combo-course__rule {
  border-radius: 999px;
  padding: 0.1rem 0.55rem;
  font-size: 0.78rem;
  background: color-mix(in srgb, var(--ion-text-color, #1c1b18) 8%, transparent);
}
.combo-course[data-required='true'] .combo-course__rule {
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 22%, transparent);
}
.combo-course__actions,
.combo-course__row-actions,
.combo-course__form-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.1rem;
}
.combo-course__subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  font-weight: 500;
  opacity: 0.8;
}
.combo-course > * {
  min-width: 0;
}
.combo-course__choices {
  display: grid;
  border-top: 1px solid var(--ion-border-color, #e7e2d6);
}
/* Wraps on purpose (the old builder measured it at 390 px): a long product name plus its supplement
   would push the row's actions past the card's edge, so on a narrow screen they drop to their own line. */
.combo-course__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
  background: var(--ion-background-color, #fff);
}
.combo-course__choice {
  display: flex;
  flex: 1 1 10rem;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.combo-course__row-actions {
  margin-left: auto;
}
.combo-course__choice-name {
  overflow-wrap: anywhere;
}
.combo-course__delta {
  font-variant-numeric: tabular-nums;
}
.combo-course__form {
  display: grid;
  grid-template-columns: minmax(12rem, 2fr) minmax(7rem, 1fr) auto;
  align-items: start;
  gap: 0.6rem;
}
@media (max-width: 640px) {
  .combo-course__form {
    grid-template-columns: 1fr;
  }
}
.combo-course__muted {
  margin: 0;
  font-size: 0.85rem;
  opacity: 0.75;
}
.combo-course__editing {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 500;
}
.combo-course__reason {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger, #c5000f);
}
</style>
