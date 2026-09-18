<template>
  <!-- hub#1905 — the end of a template import asks for the permissions of the apps it brought.
       Only opens when there is something to ask; nothing is granted without the click. -->
  <ion-modal
    :is-open="open"
    :backdrop-dismiss="!granting"
    data-testid="import-permissions"
    @did-dismiss="later"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ t('importPermissions.title') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <p class="mb-3">{{ t('importPermissions.intro') }}</p>
      <ion-list
        v-for="group in groups"
        :key="group.moduleId"
        lines="full"
        data-testid="import-permissions-app"
        :data-module="group.moduleId"
      >
        <ion-list-header>
          <ion-label>{{ appLabel(group.moduleId, appNames) }}</ion-label>
        </ion-list-header>
        <ion-item v-for="cap in group.capabilities" :key="cap.id">
          <HubIcon slot="start" name="shield-checkmark-outline" />
          <ion-label class="ion-text-wrap">
            <h2>{{ cap.label }}</h2>
            <p>{{ cap.description }}</p>
            <!-- What stops working without it, in the same words Settings → Permissions uses. -->
            <p class="consent-breaks">{{ t(capabilityBreaksKey(cap.id)) }}</p>
          </ion-label>
        </ion-item>
      </ion-list>
      <p v-if="failedMessage" role="alert" class="consent-error" data-testid="import-permissions-error">
        {{ failedMessage }}
      </p>
      <ion-button
        class="mt-3"
        expand="block"
        :disabled="granting"
        data-testid="import-permissions-grant"
        @click="grant"
      >
        <ion-spinner v-if="granting" slot="start" name="crescent" />
        <HubIcon v-else slot="start" name="shield-checkmark-outline" />
        {{ granting ? t('importPermissions.granting') : t('importPermissions.grant') }}
      </ion-button>
      <ion-button
        class="mt-2"
        expand="block"
        fill="clear"
        :disabled="granting"
        data-testid="import-permissions-later"
        @click="later"
      >
        {{ t('importPermissions.later') }}
      </ion-button>
    </ion-content>
  </ion-modal>
</template>

<script setup lang="ts">
// The question a template import owes the owner (hub#1905): «these apps need your permission».
//
// A template never grants a permission by itself — the runtime refuses the grants of another
// hub's bundle on purpose (hub#473). The store asks when ONE app is installed (`AppsPage`, pm#132);
// an import installs several and asked nothing, so a salon came out of «Peluquería» with VeriFactu
// and Printing switched off: its first sale had no fiscal record and its receipt never printed.
//
// Shared by both doors that import a template — the hero card of an empty business and Settings ›
// Data — so the question is the same wherever the import ran. What to ask and what failed is
// decided in `lib/import-permissions.ts`; this only paints and clicks.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonButton,
  IonContent,
  IonHeader,
  IonItem,
  IonLabel,
  IonList,
  IonListHeader,
  IonModal,
  IonSpinner,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';

import HubIcon from './HubIcon.vue';
import { appLabel, loadAppNames, type AppNames } from '../lib/app-names';
import { appsToAsk, grantPending, pendingPermissions, type PermissionGroup } from '../lib/import-permissions';
import { capabilityBreaksKey } from '../lib/module-capabilities';
import {
  getClient,
  getModuleCapabilities,
  putModuleCapabilities,
  type ImportReport,
} from '../lib/runtime';
import { refreshSetupStatus } from '../lib/setup-status';

const props = defineProps<{
  /** The report of the import that just finished. `null` while there is none. */
  report: ImportReport | null;
}>();
const emit = defineEmits<{ granted: [] }>();

const { t } = useI18n();

const open = ref<boolean>(false);
const groups = ref<PermissionGroup[]>([]);
const granting = ref<boolean>(false);
/** Apps whose grant the runtime refused on the last click. */
const failed = ref<string[]>([]);
const appNames = ref<AppNames>(new Map());

const failedMessage = computed<string>(() =>
  failed.value.length
    ? t('importPermissions.grantError', {
        apps: failed.value.map((id) => appLabel(id, appNames.value)).join(', '),
      })
    : '',
);

watch(
  () => props.report,
  (report) => {
    void ask(report);
  },
  { immediate: true },
);

async function ask(report: ImportReport | null): Promise<void> {
  const ids = appsToAsk(report);
  if (!ids.length) return;
  const [pending, names] = await Promise.all([
    pendingPermissions(ids, async (id) => (await getModuleCapabilities(id)).capabilities),
    loadAppNames(),
  ]);
  // A newer import finished while this one was being read: that one asks, not this one.
  if (report !== props.report) return;
  appNames.value = names;
  groups.value = pending;
  failed.value = [];
  open.value = pending.length > 0;
}

async function grant(): Promise<void> {
  if (granting.value) return;
  granting.value = true;
  try {
    const refused = await grantPending(groups.value, putModuleCapabilities);
    // Whatever was granted changes the checklist below («Configure VeriFactu» stops waiting on
    // the switch), so it re-reads even when something was refused.
    void refreshSetupStatus(getClient());
    if (refused.length) {
      groups.value = refused;
      failed.value = refused.map((g) => g.moduleId);
      return;
    }
    close();
    emit('granted');
  } finally {
    granting.value = false;
  }
}

/** «Not now»: nothing is granted. The checklist keeps saying which app waits on a permission. */
function later(): void {
  if (granting.value) return;
  close();
}

function close(): void {
  open.value = false;
  groups.value = [];
  failed.value = [];
}
</script>

<style scoped>
.consent-breaks {
  color: var(--ion-color-medium);
}
.consent-error {
  margin: 0.75rem 0 0;
  color: var(--ion-color-danger-shade, #ad000d);
}
</style>
