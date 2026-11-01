<script setup lang="ts">
// System › «Usage and plan» (BASE-F40; it joins the old Resources and «Plan and limits»), for who runs the business (the
// page tells anyone else who may see it): the live `base.plan.usage`, so whoever opens it knows in one line whether to
// upgrade (`lib/plan-usage.ts`), then what the plan includes, the fullest first, and what no plan limits. The assistant's
// messages wait on erplora.com, so they are asked apart, once the plan is known, and failing only touches their own row.
// «Upgrade plan» goes by BASE-F11's rule (`lib/plan-link.ts`). What was not measured yet says so, never with a zero; a demo
// says it is not measured; without the plan, what is in use goes with no limit, bar, pill or verdict.
import { InlineFeedback, StatusPill, UsageMeter } from '@erplora/ui/components';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { openExternalLink } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { formatSize } from '../lib/files';
import { useBaseI18n } from '../lib/i18n';
import { usePlanLink } from '../lib/plan-link';
import { type AssistantRead, type Motive, usageRows, type UsageRow, verdictOf } from '../lib/plan-usage';

const { t, locale } = useBaseI18n();
const client = useLiveClient();

const { data: usage, status, refresh } = useLive('base.plan.usage', {});
const failed = computed(() => status.value === 'error' && usage.value === undefined);
const { planUrl, offered } = usePlanLink();

const assistant = ref<AssistantRead>(null);
let asked = false;
watch(
  () => usage.value?.known === true,
  (known) => {
    if (!known || asked) return;
    asked = true;
    client.api.call('base.assistant.usage', {}).then(
      (read) => {
        assistant.value = read;
      },
      (error: unknown) => {
        console.warn('base: the assistant’s messages could not be read', error);
        assistant.value = 'failed';
      },
    );
  },
  { immediate: true },
);

function onDay(day: string): string {
  // A UTC day (`YYYY-MM-DD`), said as that day wherever the screen is.
  const date = new Date(`${day}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? day : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeZone: 'UTC' }).format(date);
}

const number = (figure: number) => new Intl.NumberFormat(locale.value).format(figure);
const size = (bytes: number) => formatSize(bytes, locale.value);
const measuredOn = (day: string) => t('base.system.usage.measuredOn', { day: onDay(day) });
const since = (day: string) => t('base.system.usage.since', { day: onDay(day) });

const KNOWN_PLANS = new Set(['free', 'starter', 'standard', 'pro', 'enterprise', 'max']);
const planName = computed(() => {
  const slug = usage.value?.plan_slug ?? '';
  return KNOWN_PLANS.has(slug) ? t(`base.system.usage.planNames.${slug}`) : slug.charAt(0).toUpperCase() + slug.slice(1);
});

const verdict = computed(() => (usage.value?.known ? verdictOf(usage.value, assistant.value) : null));
const rows = computed(() => (usage.value ? usageRows(usage.value, assistant.value) : []));

function motiveText(motive: Motive): string {
  const said = 'base.system.usage.motive';
  if (motive.kind === 'capacity') return t(`${said}.capacity`);
  const state = motive.tone === 'danger' ? 'Full' : 'Near';
  return motive.kind === 'meter' ? t(`${said}.meter${state}`, { name: motive.label ?? '' }) : t(`${said}.${motive.kind}${state}`);
}

const verdictLine = computed(() => {
  const { motive } = verdict.value ?? {};
  if (!motive) return t('base.system.usage.verdict.enough');
  return t(`base.system.usage.verdict.${motive.tone === 'danger' ? 'must' : 'should'}`, { motive: motiveText(motive) });
});

const fullLine = computed(() => {
  const full = verdict.value?.tone === 'success' ? verdict.value.full : [];
  if (full.length === 0) return null;
  const words = full.map((thing) => t(`base.system.usage.rows.${thing}`));
  const things = new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(words);
  return t('base.system.usage.verdict.full', { things });
});

function rowName(row: UsageRow): string {
  return row.kind === 'meter' ? (row.label ?? '') : t(`base.system.usage.rows.${row.kind}`);
}

function figure(row: UsageRow, value: number): string {
  return row.kind === 'files' ? size(value) : number(value);
}

function rowAmount(row: UsageRow): string {
  const said = 'base.system.usage';
  switch (row.state) {
    case 'loading':
      return t(`${said}.amount.loading`);
    case 'unavailable':
      return t(`${said}.amount.unavailable`);
    case 'notIncluded':
      return row.kind === 'meter'
        ? t(`${said}.amount.notIncluded`, { name: row.label ?? '' })
        : t(`${said}.amount.notIncludedAssistant`);
    case 'notMeasured':
      if (row.kind === 'files') return t(`${said}.notMeasuredYet`);
      return row.kind === 'capacity' ? t(`${said}.notMeasuredToday`) : t(`${said}.notMeasured`);
    case 'plain':
      return row.kind === 'capacity'
        ? t(`${said}.amount.connectionsOpen`, { used: number(row.used ?? 0), n: row.used ?? 0 })
        : figure(row, row.used ?? 0);
    case 'noLimit':
      return t(`${said}.amount.noLimit`, { used: figure(row, row.used ?? 0) });
    default: {
      const used = figure(row, row.used ?? 0);
      const limit = figure(row, row.limit ?? 0);
      if (row.kind === 'capacity') return t(`${said}.amount.connections`, { used, limit });
      const perMonth = row.kind === 'assistant' || row.kind === 'meter';
      return t(`${said}.amount.${perMonth ? 'perMonth' : 'of'}`, { used, limit });
    }
  }
}

/** The small print of a row: when the night measured it, and what capacity has to say. */
function rowNotes(row: UsageRow): string[] {
  const value = usage.value;
  if (!value) return [];
  if (row.kind === 'files') return value.files.day ? [measuredOn(value.files.day)] : [];
  if (row.kind !== 'capacity') return [];
  const { busy_last_7_days: busy, busy_since: from, bigger_plan_gives_more: bigger } = value.connections;
  if (!busy) return [];
  const short = t('base.system.usage.fellShort', { count: number(busy), n: busy });
  const notes = [from ? `${short} · ${since(from)}` : short];
  if (value.known && !bigger) notes.push(t('base.system.usage.topCapacity'));
  return notes;
}

const PILL_TONE = { near: 'warning', full: 'danger' } as const;
function pillTone(row: UsageRow) {
  // At their limit, people, devices and apps change no colour: a Free business with its one device in use is fine.
  return row.pill === 'full' && row.tone !== 'danger' ? 'neutral' : PILL_TONE[row.pill ?? 'near'];
}
</script>

<template>
  <section class="system-usage">
    <p
      v-if="usage === undefined && !failed"
      class="system-usage-muted"
      data-testid="system-usage-loading"
      role="status"
    >
      {{ t('base.system.usage.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="system-usage-error"
      :heading="t('base.system.error.heading')"
    >
      {{ t('base.system.error.body') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="system-usage-retry"
          @click="refresh()"
        >
          {{ t('base.system.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <InlineFeedback
      v-else-if="usage?.demo"
      tone="info"
      data-testid="system-usage-demo"
    >
      {{ t('base.system.usage.demo') }}
    </InlineFeedback>
    <template v-else-if="usage">
      <header
        v-if="usage.known"
        class="system-usage-plan"
      >
        <h2>{{ t('base.system.usage.plan', { name: planName }) }}</h2>
        <a
          v-if="offered"
          class="system-usage-upgrade"
          data-testid="system-usage-upgrade"
          :href="planUrl"
          target="_blank"
          rel="noopener"
          @click="openExternalLink(planUrl, $event)"
        >{{ t('base.plan.upgrade') }}</a>
        <p
          v-else
          class="system-usage-muted"
          data-testid="system-usage-managed"
        >
          {{ t('base.system.usage.managed') }}
        </p>
      </header>
      <InlineFeedback
        v-if="verdict"
        :tone="verdict.tone"
        data-testid="system-usage-verdict"
        :heading="verdictLine"
      >
        <template v-if="fullLine">
          {{ fullLine }}
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-else
        tone="info"
        data-testid="system-usage-unknown"
      >
        {{ t('base.system.usage.unknown') }}
      </InlineFeedback>

      <h3
        class="system-usage-heading"
        data-testid="system-usage-included-heading"
      >
        {{ t(usage.known ? 'base.system.usage.included' : 'base.system.usage.using') }}
      </h3>
      <ul class="system-usage-rows">
        <li
          v-for="row in rows"
          :key="row.id"
          class="system-usage-row"
          :data-testid="`system-usage-row-${row.id}`"
        >
          <span class="system-usage-name">{{ rowName(row) }}</span>
          <span class="system-usage-amount">{{ rowAmount(row) }}</span>
          <span class="system-usage-bar">
            <UsageMeter
              v-if="row.percent !== null"
              size="sm"
              :label="rowAmount(row)"
              :percent="row.percent"
              :tone="row.tone"
              :locale="locale"
            />
          </span>
          <span class="system-usage-pill">
            <StatusPill
              v-if="row.pill"
              :tone="pillTone(row)"
              :label="t(`base.system.usage.pill.${row.pill}`)"
            />
          </span>
          <span
            v-for="note in rowNotes(row)"
            :key="note"
            class="system-usage-note"
          >{{ note }}</span>
        </li>
      </ul>

      <h3
        class="system-usage-heading"
        data-testid="system-usage-information-heading"
      >
        {{ t('base.system.usage.information') }}
      </h3>
      <ul
        class="system-usage-rows"
        data-testid="system-usage-information"
      >
        <li
          class="system-usage-row system-usage-row--info"
          data-testid="system-usage-info-requests"
        >
          <span class="system-usage-name">{{ t('base.system.usage.info.requests') }}</span>
          <span class="system-usage-amount">{{
            usage.requests.this_month === null ? t('base.system.usage.notMeasuredToday') : number(usage.requests.this_month)
          }}</span>
          <span
            v-if="usage.requests.since"
            class="system-usage-note"
          >{{ since(usage.requests.since) }}</span>
        </li>
        <li
          class="system-usage-row system-usage-row--info"
          data-testid="system-usage-info-active"
        >
          <span class="system-usage-name">{{ t('base.system.usage.info.active') }}</span>
          <span class="system-usage-amount">{{ number(usage.activity.active_now ?? 0) }}</span>
        </li>
        <li
          class="system-usage-row system-usage-row--info"
          data-testid="system-usage-info-month"
        >
          <span class="system-usage-name">{{ t('base.system.usage.info.month') }}</span>
          <span class="system-usage-amount">{{
            usage.activity.last_30_days === null ? t('base.system.usage.notMeasuredYet') : number(usage.activity.last_30_days)
          }}</span>
          <span
            v-if="usage.activity.day"
            class="system-usage-note"
          >{{ measuredOn(usage.activity.day) }}</span>
        </li>
        <li
          class="system-usage-row system-usage-row--info"
          data-testid="system-usage-info-database"
        >
          <span class="system-usage-name">{{ t('base.system.usage.info.database') }}</span>
          <span class="system-usage-amount">{{
            usage.database.bytes === null ? t('base.system.usage.notMeasuredYet') : size(usage.database.bytes)
          }}</span>
          <span
            v-if="usage.database.day"
            class="system-usage-note"
          >{{ measuredOn(usage.database.day) }}</span>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.system-usage {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.system-usage-plan {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
}

.system-usage-plan h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.system-usage-upgrade {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ion-color-primary);
  white-space: nowrap;
}

.system-usage-heading {
  margin: 8px 0 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.system-usage-rows {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  list-style: none;
}

.system-usage-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 12px;
  align-items: center;
  padding: 12px 16px;
}

.system-usage-row + .system-usage-row {
  border-top: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
}

.system-usage-name {
  font-weight: 600;
}

.system-usage-amount {
  grid-column: 1;
  min-width: 0;
}

.system-usage-row--info .system-usage-amount {
  grid-column: 2;
  grid-row: 1;
  justify-self: end;
  text-align: end;
  font-weight: 600;
}

.system-usage-pill {
  grid-column: 2;
  grid-row: 1;
  justify-self: end;
}

.system-usage-bar {
  grid-column: 1 / -1;
  min-width: 0;
}

.system-usage-bar:empty,
.system-usage-pill:empty {
  display: none;
}

.system-usage-note {
  grid-column: 1 / -1;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.8125rem;
}

.system-usage-muted {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

/* The amount above the bar is its name too (the accessible one); the meter's own head would say it twice, with a
   percentage that calls a Free plan's first operation 100 %. */
.system-usage-bar :deep(.usage-meter__head) {
  display: none;
}

@media (min-width: 768px) {
  .system-usage-row {
    grid-template-columns: 10rem minmax(0, 1fr) 12rem 6rem;
  }

  .system-usage-name {
    grid-column: 1;
    grid-row: 1;
  }

  .system-usage-amount {
    grid-column: 2;
    grid-row: 1;
  }

  .system-usage-bar {
    grid-column: 3;
    grid-row: 1;
  }

  .system-usage-pill {
    grid-column: 4;
    grid-row: 1;
  }

  .system-usage-note {
    grid-column: 2 / -1;
  }

  .system-usage-row--info {
    grid-template-columns: 10rem minmax(0, 1fr);
  }

  .system-usage-row--info .system-usage-amount {
    grid-column: 2;
    justify-self: start;
    text-align: start;
    font-weight: 400;
  }
}
</style>
