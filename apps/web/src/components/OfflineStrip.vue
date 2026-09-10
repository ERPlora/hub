<template>
  <!-- Nothing at all while there is a network. Not an empty box, not a spacer: this sits over
       EVERY screen of the product, the till included, so silence is the default. -->
  <ok-inline-feedback
    v-if="isOffline"
    class="offline-strip"
    tone="warning"
    icon="cloud-offline-outline"
    :heading="t('offline.title')"
    data-testid="offline-strip"
  >
    <p class="offline-strip-body">{{ t('offline.body') }}</p>
  </ok-inline-feedback>
</template>

<script setup lang="ts">
// The band that says the network is gone, and keeps saying it (hub#1743).
//
// `ModuleView` now tells «no connection» apart from «this module is broken», but only when
// something FAILS. That leaves the commonest shape of the complaint uncovered: the network drops
// while somebody is looking at a screen that already loaded, and nothing changes — the till looks
// perfectly healthy right up to the moment a sale will not go through.
//
// Every product that runs in a shop settles this the same way (Square's dashboard, Toast, Shopify
// POS; Gmail and Google Docs outside our sector): ONE persistent band, up for as long as there is
// no network, gone by itself the moment there is one. It lives in `AppPage` next to
// `SetupBlockingStrip` for the reason that strip already writes down — a warning that scrolls away
// is not a warning, and putting it in each view means the next view forgets it.
//
// **It carries no button, on purpose.** The shell is served over the internet, so reloading the
// document with no network hands the person the browser's own error page and takes the open till
// with it. `navigator.onLine` clears itself, so a retry here has nothing to do that waiting does
// not do better; the retry belongs on the screen that actually failed, and `ModuleView` has it.
//
// The announcement is not repeated here: `ok-inline-feedback` already wraps its content in a
// `role="status"` live region, and a second one on the host makes screen readers say it twice.
import { useI18n } from 'vue-i18n';

import { isOffline } from '../lib/offline';

const { t } = useI18n();
</script>

<style scoped>
/* Page chrome, not content: it lives between the topbar and the scroller so it cannot scroll away.
   `ok-inline-feedback` already brings the tonal background and the accent rail of the warning tone —
   this only gives it the margins of a band. */
.offline-strip {
  --border-radius: 0;
  --padding: 0.6rem 1rem;
  flex: none;
}
.offline-strip-body {
  margin: 0;
  font-size: 0.875rem;
}
</style>
