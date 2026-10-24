<script setup lang="ts">
// Employees › Personal (BASE-G11, G138, G142; the old hub's EmployeesPage): the live `base.person.list` — every person
// of the business once, from the top role — in a table of User (with «You»), Email (only for who runs the business),
// Role, Access (how they get in: their erplora.com account always, then a PIN and a badge) and Status (in, or named by
// erplora.com and not in yet). Above it, the plan's places taken and, when every one is, why and «Upgrade plan» (web
// only: it sells). People are invited, given a role and removed on erplora.com («Members» of the business: HUBS-F24…
// F27), which `hub-home` names only for a session opened with the account; who runs the business opens a person's
// page from the row (their PIN and badge). On a phone each person is a card. A list that cannot be read says so.
import { DataTable, type DataTableColumn, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, useSession, useSurface } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import { type HubHome, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { accessKeys, roleKey } from '../lib/people';
import type { Person } from '../operations';

const { t, locale } = useBaseI18n();
const router = useRouter();
const session = useSession();
const { isWeb } = useSurface();

const admin = computed(() => session.can('base.administer_hub'));
const home = readJsonBlock<HubHome>('hub-home');
const membersUrl = home?.members_url ?? '';
const planUrl = home?.plan_url ?? '';

const { data, status, refresh } = useLive('base.person.list', {});

const rows = computed<Person[]>(() => data.value?.people ?? []);
const seats = computed(() => data.value?.seats);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const number = (n: number) => new Intl.NumberFormat(locale.value).format(n);

const seatsText = computed(() => {
  const value = seats.value;
  if (!value) return '';
  // `n` picks the singular or the plural: of the places for «{used} of {limit}», of the people otherwise.
  if (value.limit !== null)
    return t('base.people.seats.used', { used: number(value.used), limit: number(value.limit), n: value.limit });
  return value.known
    ? t('base.people.seats.noLimit', { used: number(value.used), n: value.used })
    : t('base.people.seats.count', { used: number(value.used), n: value.used });
});

const access = (row: Person) => accessKeys(row.ways).map((key) => t(key)).join(' + ');

const columns = computed<DataTableColumn<Person>[]>(() => [
  { key: 'name', label: t('base.people.columns.person'), cell: 'person', width: 'minmax(12rem,2fr)' },
  ...(admin.value
    ? [{ key: 'email', label: t('base.people.columns.email'), width: 'minmax(12rem,2fr)', format: (value: unknown) => (value as string) || '—' }]
    : []),
  { key: 'role', label: t('base.people.columns.role'), format: (_: unknown, row: Person) => t(roleKey(row.role)), width: '10rem' },
  { key: 'access', label: t('base.people.columns.access'), cell: 'access', sortValue: access, width: '12rem' },
  { key: 'entered', label: t('base.people.columns.status'), cell: 'status', width: '10rem' },
]);

function open(row: Person): void {
  if (admin.value) void router.push(`/employees/${row.id}`);
}
</script>

<template>
  <section class="people">
    <header class="people-head">
      <p
        v-if="seats"
        class="people-seats"
        data-testid="people-seats"
      >
        {{ seatsText }}
      </p>
      <a
        v-if="admin && membersUrl"
        class="people-invite"
        data-testid="people-invite"
        :href="membersUrl"
        target="_blank"
        rel="noopener"
      >
        <HubIcon
          name="ion:person-add-outline"
          aria-hidden="true"
        />
        {{ t('base.people.invite') }}
      </a>
    </header>
    <InlineFeedback
      v-if="seats?.full"
      tone="warning"
      data-testid="people-full"
      :heading="t('base.people.full.heading')"
    >
      {{ t('base.people.full.body') }}
      <template
        v-if="isWeb && planUrl"
        #actions
      >
        <a
          class="people-upgrade"
          data-testid="people-upgrade"
          :href="planUrl"
          target="_blank"
          rel="noopener"
        >{{ t('base.plan.upgrade') }}</a>
      </template>
    </InlineFeedback>
    <p class="people-managed">
      {{ t('base.people.managed') }}
    </p>
    <DataTable
      testid="people"
      :columns="columns"
      :rows="rows"
      :page-size="20"
      :page-size-options="[]"
      :views="['table', 'cards']"
      :card-title="(row: Person) => row.name"
      card-title-column="name"
      :search-keys="['name', 'email']"
      :search-placeholder="t('base.people.search')"
      :empty-message="t('base.people.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.people.error') : undefined"
      :row-clickable="admin"
      @row-click="open"
      @retry="refresh()"
    >
      <template #person="{ row }">
        <span class="people-person">
          <span
            class="people-initials"
            aria-hidden="true"
          >{{ (row as Person).initials }}</span>
          <span class="people-name">{{ (row as Person).name }}</span>
          <StatusPill
            v-if="(row as Person).me"
            size="sm"
            tone="neutral"
            :label="t('base.people.you')"
          />
        </span>
      </template>
      <template #access="{ row }">
        <span data-testid="people-access">{{ access(row as Person) }}</span>
      </template>
      <template #status="{ row }">
        <StatusPill
          data-testid="people-status"
          size="sm"
          :tone="(row as Person).entered ? 'success' : 'neutral'"
          :label="t((row as Person).entered ? 'base.people.status.active' : 'base.people.status.notEntered')"
        />
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.people {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.people-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.people-seats,
.people-managed {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.people-invite,
.people-upgrade {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}

.people-person {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.people-initials {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: color-mix(in oklab, var(--ion-color-primary) 14%, transparent);
  color: var(--ion-color-primary);
  font-size: 0.8125rem;
  font-weight: 600;
}

.people-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
