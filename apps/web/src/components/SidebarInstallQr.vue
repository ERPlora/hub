<!--
  hub#1715 — the door from this counter to somebody's phone.

  Until now the only way to open a hub on a phone was to read the address off the screen and type
  it in, letter by letter, standing up. That is friction at the worst possible moment: right after
  signing up, while the person is still deciding whether any of this is worth it.

  **Passive, and that is the whole point (hub#685).** The modal that used to greet everybody with
  «Get the full experience» is gone and is not coming back: what Ioan banned was the INTERRUPTION,
  not installing. A code sitting in a panel asks nothing, covers nothing and waits — it is
  something a person GOES AND DOES, which is exactly the line hub#685 drew. Nothing here listens
  for the browser's own install offer; on Chromium that offer stays where it belongs, in the
  address bar.

  **Unconditional.** No role, no permission, no plan, no module, and nothing to close. The person
  who sets up a phone is usually the one working the till, not an admin, and a code with a «don't
  show again» is a code that is gone for good on a shared device. `SidebarInstallQr.test.ts` asserts
  the ABSENCE of the condition, which is the part that has to survive the next six months.

  **The rail is CSS, not a `v-if`.** Collapsed, the panel is ~72px and a readable code needs about
  132px, so the code swaps for its icon; pressing it opens the panel back up, where the code fits.
  A dead icon would be worse than no icon, and hiding the block outright would make the affordance
  depend on a toggle nobody remembers pressing.
-->
<template>
  <div class="sidebar-install-qr" data-testid="sidebar-install-qr">
    <!-- Rail only (CSS): the icon stands in for the code, and opens the panel that can show it. -->
    <ion-button
      class="sidebar-install-qr-rail"
      fill="clear"
      size="small"
      :title="t('installQr.title')"
      :aria-label="t('installQr.title')"
      @click="onExpand"
    >
      <HubIcon name="qr-code-outline" />
    </ion-button>

    <div class="sidebar-install-qr-full">
      <!-- `ok-qr` (OutfitKit): pure-JS generator, no dependency and no `eval` — it renders under
           the hub's strict CSP, where a canvas-based library would not. `ec="M"` is the standard
           trade-off for a URL: it survives a fingerprint on the screen without inflating the
           symbol so much that the modules stop resolving on a phone camera. -->
      <ok-qr class="sidebar-install-qr-code" :value="qrUrl" size="132" ec="M" />
      <p class="sidebar-install-qr-title">{{ t('installQr.title') }}</p>
      <!-- One sentence for BOTH platforms, on purpose. The screen painting this code cannot know
           what phone will read it, so a per-platform instruction here would be a guess: Chromium
           offers to install by itself, Safari only through Share → Add to Home Screen, and both
           of those live in «your browser menu». Without this line the iPhone stops halfway and
           the code looks broken. -->
      <p class="sidebar-install-qr-hint">{{ t('installQr.hint') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

import HubIcon from './HubIcon.vue';
import { installQrUrl } from '../lib/install-qr';
import { railCollapsed } from '../lib/shell';

const { t } = useI18n();

// Read once, at mount: the shell never navigates away from its own hub, so this cannot go stale.
const qrUrl = installQrUrl(window.location);

function onExpand(): void {
  railCollapsed.value = false;
}
</script>
