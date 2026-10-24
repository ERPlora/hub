<script setup lang="ts">
// Employees (BASE-G11; the old hub's EmployeesPage, HUB_SHELL-F80…F98): the footer tabbar of its sections, the tab in
// the hash (lib/people.ts) so a link opens it and Back leaves the page instead of walking its tabs. In the old hub's
// order: «Staff» (the people and their ways in, BASE-G138…G142), «Roles» (G143, G144), «API keys» (G146…G149) and
// «Approvals» (G145); the last two only for who runs the business — for anyone else the tab does not exist and its
// hash opens «Staff». Only the open tab's panel is painted, so only it asks the hub.
import { AppPage, type ShellTab, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import ApiKeysPanel from '../components/ApiKeysPanel.vue';
import ApprovalsList from '../components/ApprovalsList.vue';
import PeopleList from '../components/PeopleList.vue';
import RolesList from '../components/RolesList.vue';
import { useBaseI18n } from '../lib/i18n';
import { EMPLOYEES_TAB_HASH, type EmployeesTab, employeesTabOf, employeesTabsFor } from '../lib/people';
import '../settings.css';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const admin = computed(() => session.can('base.administer_hub'));

const ICONS: Record<EmployeesTab, string> = {
  personal: 'ion:people-outline',
  roles: 'ion:shield-checkmark-outline',
  apikeys: 'ion:keypad-outline',
  approvals: 'ion:finger-print-outline',
};

const tabs = computed<ShellTab[]>(() =>
  employeesTabsFor(admin.value).map((id) => ({ id, label: t(`base.employees.tabs.${id}`), icon: ICONS[id] })),
);
const tab = computed<EmployeesTab>({
  get: () => employeesTabOf(route.hash, admin.value),
  set: (next) => void router.replace({ path: route.path, query: route.query, hash: EMPLOYEES_TAB_HASH[next] }),
});
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.employees.title')"
    :tabs="tabs"
    :tabs-label="t('base.employees.tabs.label')"
    content-layout="detail"
  >
    <PeopleList v-if="tab === 'personal'" />
    <RolesList v-else-if="tab === 'roles'" />
    <ApiKeysPanel v-else-if="tab === 'apikeys'" />
    <ApprovalsList v-else-if="tab === 'approvals'" />
  </AppPage>
</template>
