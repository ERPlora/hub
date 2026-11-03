<script setup lang="ts">
// Employees › Roles (BASE-G143, G144; the old hub's RolesPanel): the live `base.role.list` — erplora.com's four roles,
// from the top — with where each comes from («Basic»: the business's own, always available), how many people have it
// and how many permissions of the apps it gives. A role is given when a person is invited on erplora.com, and changed
// there (HUBS-F24, F26): who runs the business opens its «Members». No module brings a role of its own today, so there is
// nothing to turn on or off (the old switch of an app's role). A catalogue that cannot be read says so. The link leaves
// the Hub by `openExternalLink` (in the installed app, the system browser: gh:hub#439) and, a way to erplora.com's
// panel, never in the Google Play copy (`managementOffered`, gh:hub#1897).
import { DataTable, type DataTableColumn, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { openExternalLink, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import { type HubHome, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { managementOffered } from '../lib/management';
import { roleKey } from '../lib/people';
import type { HubRoleRow } from '../operations';

const { t, locale } = useBaseI18n();
const session = useSession();
const admin = computed(() => session.can('base.administer_hub'));
const membersUrl = readJsonBlock<HubHome>('hub-home')?.members_url ?? '';
const offered = managementOffered();

const { data, status, refresh } = useLive('base.role.list', {});

const rows = computed<HubRoleRow[]>(() => data.value?.roles ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const number = (n: number) => new Intl.NumberFormat(locale.value).format(n);

const columns = computed<DataTableColumn<HubRoleRow>[]>(() => [
  { key: 'key', label: t('base.roles.columns.role'), format: (_, row) => t(roleKey(row.key)), width: 'minmax(10rem,2fr)' },
  { key: 'origin', label: t('base.roles.columns.origin'), cell: 'origin', width: '8rem', sortable: false },
  { key: 'available', label: t('base.roles.columns.available'), cell: 'available', width: '12rem', sortable: false },
  { key: 'members', label: t('base.roles.columns.members'), cell: 'members', align: 'right', width: '8rem' },
  { key: 'permissions', label: t('base.roles.columns.permissions'), cell: 'permissions', align: 'right', width: '8rem' },
]);
</script>

<template>
  <section class="roles">
    <header class="roles-head">
      <p class="roles-intro">
        {{ t('base.roles.intro') }}
      </p>
      <a
        v-if="admin && membersUrl && offered"
        class="roles-change"
        data-testid="roles-change"
        :href="membersUrl"
        target="_blank"
        rel="noopener"
        @click="openExternalLink(membersUrl, $event)"
      >{{ t('base.roles.change') }}</a>
    </header>
    <DataTable
      testid="roles"
      row-key="key"
      :columns="columns"
      :rows="rows"
      :page-size="10"
      :page-size-options="[]"
      :views="['table', 'cards']"
      :card-title="(row: HubRoleRow) => t(roleKey(row.key))"
      card-title-column="key"
      :search-keys="['label']"
      :search-placeholder="t('base.roles.search')"
      :empty-message="t('base.roles.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.roles.error') : undefined"
      @retry="refresh()"
    >
      <template #origin>
        <StatusPill
          size="sm"
          tone="neutral"
          :label="t('base.roles.basic')"
        />
      </template>
      <template #available>
        <StatusPill
          size="sm"
          tone="success"
          :label="t('base.roles.always')"
        />
      </template>
      <template #members="{ row }">
        <span data-testid="roles-members">{{ number((row as HubRoleRow).members) }}</span>
      </template>
      <template #permissions="{ row }">
        <span data-testid="roles-permissions">{{ number((row as HubRoleRow).permissions) }}</span>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.roles {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.roles-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.roles-intro {
  flex: 1 1 20rem;
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.roles-change {
  padding: 8px 14px;
  border: 1px solid var(--ion-color-primary);
  border-radius: var(--ep-radius, 12px);
  color: var(--ion-color-primary);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}
</style>
