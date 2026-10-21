<script setup lang="ts">
// SERVICE-F31, F32 «Profesionales que lo hacen» (the old Staff record's «Servicios que realiza», now on
// the service, as Fresha, Square or Vagaro): the live `service.assignment.list` of the service, each
// with what it lasts and costs with that person and their main service marked. Whoever may edit
// services assigns someone of Staff (searched on the server) with their own minutes and price, changes
// those (empty = the service's), marks the main service, switches one off or removes it. Changes come
// back through the stream; a refusal is said above the list. Until the list arrives it says it is
// loading; a list that cannot be read says so, with the reason and «Retry».
import { Combo, type ComboOption, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchMembers } from '../lib/pickers';
import type { AssignmentOut } from '../operations';
import MoneyInput from './MoneyInput.vue';

const props = defineProps<{
  serviceId: string;
  /** May edit services (`service.change_service`): assign, change and remove. */
  canChange: boolean;
}>();

interface Draft {
  minutes: string;
  price: string;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const searchStaff = searchMembers(client);

const { data, status, error: loadFailure, refresh } = useLive('service.assignment.list', () => ({ service_id: props.serviceId, limit: 100 }));
const rows = computed<AssignmentOut[]>(() => data.value?.rows ?? []);
/** The people of Staff who do not perform the service yet (WORKBOOK SERVICE-F31). */
const searchPeople = async (query: string): Promise<ComboOption[]> => {
  const assigned = new Set(rows.value.map((row) => row.member_id));
  return (await searchStaff(query)).filter((option) => !assigned.has(option.id));
};

const assign = useCommand('service.assignment.assign');
const update = useCommand('service.assignment.update');
const remove = useCommand('service.assignment.remove');
const failure = ref<ApiError | null>(null);

const newcomer = ref<{ member: ComboOption | null; minutes: string; price: string }>({ member: null, minutes: '', price: '' });
const drafts = ref<Record<string, Draft>>({});

const ownOf = (row: AssignmentOut): Draft => ({
  minutes: row.custom_duration === null ? '' : String(row.custom_duration),
  price: moneyFieldText(row.custom_price, locale.value),
});

// What the server says resets the rows the person is not editing.
watch(
  rows,
  (now) => {
    const next: Record<string, Draft> = {};
    for (const row of now) next[row.id] = changed(row) ? drafts.value[row.id] : ownOf(row);
    drafts.value = next;
  },
  { immediate: true },
);

function changed(row: AssignmentOut): boolean {
  const draft = drafts.value[row.id];
  if (!draft) return false;
  const own = ownOf(row);
  return draft.minutes.trim() !== own.minutes || draft.price.trim() !== own.price;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
/** Whole minutes as the server takes them (empty = none); anything else as typed, for the server to refuse. */
const minutes = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return /^\d+$/.test(trimmed) ? Number(trimmed) : (trimmed as unknown as number);
};
/** Cents of a price field (empty = none); `undefined` when it is not an amount (the field says why). */
const cents = (value: string): number | null | undefined => {
  const read = parseMoney(value);
  return read.ok ? read.cents : undefined;
};

async function act(run: () => Promise<unknown>, error: () => ApiError | null): Promise<boolean> {
  failure.value = null;
  try {
    await run();
    return true;
  } catch {
    failure.value = error();
    return false;
  }
}

async function addPerson(): Promise<void> {
  const { member, minutes: typed, price } = newcomer.value;
  const custom = cents(price);
  if (!member || custom === undefined) return;
  const body = {
    service_id: props.serviceId,
    member_id: member.id,
    ...(typed.trim() ? { custom_duration: minutes(typed) } : {}),
    ...(custom !== null ? { custom_price: custom } : {}),
  };
  if (await act(() => assign.run(body), () => assign.error.value)) newcomer.value = { member: null, minutes: '', price: '' };
}

async function saveOwn(row: AssignmentOut): Promise<void> {
  const draft = drafts.value[row.id];
  const custom = cents(draft.price);
  if (custom === undefined) return;
  const own = ownOf(row);
  const body = {
    id: row.id,
    ...(draft.minutes.trim() !== own.minutes ? { custom_duration: minutes(draft.minutes) } : {}),
    ...(draft.price.trim() !== own.price ? { custom_price: custom } : {}),
  };
  if (await act(() => update.run(body), () => update.error.value)) drafts.value = { ...drafts.value, [row.id]: draft };
}

const setDraft = (id: string, part: Partial<Draft>) => {
  drafts.value = { ...drafts.value, [id]: { ...drafts.value[id], ...part } };
};
</script>

<template>
  <section
    class="service-professionals"
    data-testid="service-professionals"
  >
    <h3 class="service-professionals__title">
      {{ $t('service.professionals.title') }}
    </h3>
    <InlineFeedback
      v-if="failure"
      tone="danger"
      data-testid="service-professionals-error"
      :heading="t('service.professionals.error')"
    >
      {{ failure.message }}
    </InlineFeedback>
    <InlineFeedback
      v-if="status === 'error'"
      tone="danger"
      data-testid="service-professionals-load-error"
      :heading="t('service.professionals.loadError')"
    >
      {{ loadFailure?.message }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="service-professionals-retry"
          @click="refresh()"
        >
          {{ $t('service.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <p
      v-else-if="data === undefined"
      class="service-professionals__empty"
      data-testid="service-professionals-loading"
    >
      {{ $t('service.loading') }}
    </p>
    <p
      v-if="data && rows.length === 0"
      class="service-professionals__empty"
      data-testid="service-professionals-empty"
    >
      {{ $t('service.professionals.empty') }}
    </p>
    <ul class="service-professionals__list">
      <li
        v-for="row in rows"
        :key="row.id"
        class="service-professionals__row"
        :data-testid="`service-professionals-row-${row.id}`"
      >
        <div class="service-professionals__who">
          <strong>{{ row.member_name }}</strong>
          <span class="service-professionals__own">
            {{ t('service.professionals.own', { duration: row.duration, price: formatMoney(row.price, locale) }) }}
          </span>
          <StatusPill
            v-if="row.is_primary"
            size="sm"
            tone="info"
            :data-testid="`service-professionals-primary-${row.id}`"
            :label="t('service.professionals.primary')"
          />
        </div>
        <div
          v-if="canChange"
          class="service-professionals__edit"
        >
          <ion-input
            :data-testid="`service-professionals-minutes-${row.id}`"
            type="number"
            inputmode="numeric"
            min="1"
            :value="drafts[row.id]?.minutes"
            :label="$t('service.professionals.minutes')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-input="setDraft(row.id, { minutes: text($event.detail.value) })"
          />
          <MoneyInput
            :testid="`service-professionals-price-${row.id}`"
            :model-value="drafts[row.id]?.price ?? ''"
            :label="t('service.professionals.price')"
            @update:model-value="setDraft(row.id, { price: $event })"
          />
          <ion-button
            :data-testid="`service-professionals-save-${row.id}`"
            size="small"
            fill="outline"
            :disabled="!changed(row) || update.pending.value"
            @click="saveOwn(row)"
          >
            {{ $t('service.professionals.save') }}
          </ion-button>
          <ion-toggle
            :data-testid="`service-professionals-active-${row.id}`"
            label-placement="end"
            justify="start"
            :checked="row.is_active"
            @ion-change="act(() => update.run({ id: row.id, is_active: $event.detail.checked }), () => update.error.value)"
          >
            {{ $t('service.professionals.active') }}
          </ion-toggle>
          <ion-button
            v-if="!row.is_primary"
            :data-testid="`service-professionals-make-primary-${row.id}`"
            size="small"
            fill="clear"
            @click="act(() => update.run({ id: row.id, is_primary: true }), () => update.error.value)"
          >
            {{ $t('service.professionals.makePrimary') }}
          </ion-button>
          <ion-button
            :data-testid="`service-professionals-remove-${row.id}`"
            size="small"
            fill="clear"
            color="danger"
            @click="act(() => remove.run({ id: row.id }), () => remove.error.value)"
          >
            {{ $t('service.professionals.remove') }}
          </ion-button>
        </div>
      </li>
    </ul>
    <div
      v-if="canChange"
      class="service-professionals__add"
    >
      <Combo
        testid="service-professionals-member"
        :model-value="newcomer.member"
        :search="searchPeople"
        :label="t('service.professionals.add')"
        @update:model-value="newcomer = { ...newcomer, member: $event }"
      />
      <ion-input
        data-testid="service-professionals-minutes"
        type="number"
        inputmode="numeric"
        min="1"
        :value="newcomer.minutes"
        :label="$t('service.professionals.minutes')"
        label-placement="floating"
        fill="outline"
        mode="md"
        @ion-input="newcomer = { ...newcomer, minutes: text($event.detail.value) }"
      />
      <MoneyInput
        v-model="newcomer.price"
        testid="service-professionals-price"
        :label="t('service.professionals.price')"
      />
      <ion-button
        data-testid="service-professionals-assign"
        :disabled="!newcomer.member || assign.pending.value"
        @click="addPerson"
      >
        {{ $t('service.professionals.assign') }}
      </ion-button>
    </div>
  </section>
</template>

<style scoped>
.service-professionals {
  display: grid;
  gap: 10px;
  margin-top: 8px;
}
.service-professionals__title {
  margin: 8px 0 0;
  font-size: 1rem;
  font-weight: 600;
}
.service-professionals__empty {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.service-professionals__list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.service-professionals__row {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--ion-border-color, #e5e3dd);
  border-radius: 10px;
}
.service-professionals__who {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.service-professionals__own {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
/* Wide enough for «Minutes (optional)» to read whole; whoever is being added gets a row of their own. */
.service-professionals__edit,
.service-professionals__add {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  align-items: center;
  gap: 8px;
}
.service-professionals__add > :first-child {
  grid-column: 1 / -1;
}
</style>
