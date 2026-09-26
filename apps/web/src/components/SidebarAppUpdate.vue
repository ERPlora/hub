<!--
  The one visible half of hub#400: the way a till learns that the app it runs is not the one we
  publish, and the only door it has to do something about it.

  **In the left sidebar, on purpose.** The issue is explicit — visible, not buried in settings. A
  till is used standing up by whoever is on shift; anything three taps deep is something nobody ever
  finds, and the fleet stays on an old build until it breaks.

  **It only appears when all three things are true**, and each absence is a different sentence the
  product must NOT say:
   · there is a newer build (`attention`) — `unknown` is silence, never an alarm and never a green;
   · this device has somewhere to get it — otherwise it is a button that leads to a 404;
   · this session administers (ADR-0248) — a task that is not yours goes away, it is not greyed out.

  **It never updates in place.** There is no signing key yet (hub#394), so there is no Tauri
  updater: what actually happens is a download in the user's OWN browser, which they run when they
  choose. That is why the confirmation says it in those words — "updating…" would be a promise the
  product cannot keep — and why nothing here reloads, navigates or closes anything. A waiter halfway
  through an order keeps the order: this page stays exactly where it was, and the moment the till
  goes down is a moment a human picks. `app-update-does-not-interrupt.test.ts` holds that line.
-->
<template>
  <ion-item
    v-if="offered"
    button
    data-testid="sidebar-app-update"
    class="nav-item nav-item-update"
    :detail="false"
    :title="label"
    :aria-label="label"
    @click="onUpdate"
  >
    <HubIcon slot="start" class="nav-icon" name="cloud-download-outline" />
    <ion-label class="nav-label">{{ label }}</ion-label>
  </ion-item>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { alertController, IonItem, IonLabel } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

import HubIcon from './HubIcon.vue';
import { appUpdate, appUpdateDestination, appUpdatePlatform, canUpdateApp } from '../lib/app-update';
import { openExternal } from '../lib/open-external';
import { toastError } from '../lib/toast';

const { t } = useI18n();

const offered = computed(
  () =>
    appUpdate.value.state === 'attention' &&
    appUpdateDestination.value !== null &&
    canUpdateApp.value,
);

const label = computed(() => t('appUpdate.available', { version: appUpdate.value.latest ?? '' }));

// On Android the Cloud's page hands over to Google Play: no file is downloaded and nothing is opened
// afterwards, so the desktop sentence would be a promise the product does not keep (hub#1898).
const copy = computed(() => (appUpdatePlatform.value === 'android' ? 'appUpdate.android' : 'appUpdate'));

async function onUpdate(): Promise<void> {
  const destination = appUpdateDestination.value;
  if (!destination) return;

  const alert = await alertController.create({
    header: t('appUpdate.confirmTitle'),
    message: t(`${copy.value}.confirmBody`, { version: appUpdate.value.latest ?? '' }),
    buttons: [
      { text: t('appUpdate.cancel'), role: 'cancel' },
      { text: t(`${copy.value}.action`), role: 'confirm' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  if (role !== 'confirm') return;

  try {
    // The user's own browser, never this window. Inside the installed app this is the ONLY way out
    // (ADR-0255): `window.open` opens nothing there, and the address is the Cloud's — which is both
    // what the shell will accept and what redirects to the store the day a listing goes live.
    await openExternal(destination);
  } catch {
    // A press that does nothing, with no window and no error, is the defect hub#475 ended.
    void toastError(t(`${copy.value}.failed`));
  }
}
</script>
