<script setup lang="ts">
// The ⋮ SCREEN menu (not a sale menu) at the end of the category strip: its one item puts the page on
// the browser's full screen, or takes it off (the whole page: the sheets live in the app's root). The label follows the real state (the toggle, Esc, F11),
// never a local guess. Where the device cannot (an iPhone's Safari) there is no menu at all. Anchored
// under its button; a tap anywhere else, Escape or Android's Back closes it.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { onBeforeUnmount, shallowRef } from 'vue';

import { useSystemBack } from '../../composables/pos/useSystemBack';
import { isActive, isCapable, onChange, toggle } from '../../lib/fullscreen';

const open = shallowRef(false);
const anchor = shallowRef<Event>();
useSystemBack(open, () => (open.value = false));
const capable = isCapable();
const active = shallowRef(isActive());
const stop = onChange(() => (active.value = isActive()));
onBeforeUnmount(stop);

function present(event: Event): void {
  anchor.value = event;
  open.value = true;
}

function choose(): void {
  open.value = false;
  void toggle();
}
</script>

<template>
  <div
    v-if="capable"
    class="pos-more"
  >
    <ion-button
      fill="outline"
      class="pos-more__trigger"
      data-testid="pos-screen-menu"
      :aria-label="$t('sale.pos.screenMenu')"
      :title="$t('sale.pos.screenMenu')"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      @click="present"
    >
      <HubIcon
        slot="icon-only"
        name="ion:ellipsis-vertical"
      />
    </ion-button>
    <ion-popover
      :is-open="open"
      :event="anchor"
      :dismiss-on-select="true"
      @did-dismiss="open = false"
    >
      <ion-list
        class="pos-more__menu"
        lines="none"
        data-testid="pos-screen-menu-list"
        @keydown.esc="open = false"
      >
        <ion-item
          button
          :detail="false"
          data-testid="pos-fullscreen"
          @click="choose"
        >
          <HubIcon
            slot="start"
            name="ion:chevron-expand-outline"
          />
          <ion-label>{{ active ? $t('sale.pos.exitFullscreen') : $t('sale.pos.fullscreen') }}</ion-label>
        </ion-item>
      </ion-list>
    </ion-popover>
  </div>
</template>

<style scoped>
.pos-more {
  position: relative;
  flex: none;
}
.pos-more__trigger {
  width: 2.6rem;
  height: 3.65rem;
  margin: 0;
  font-size: 1.2rem;
  --color: var(--ion-color-medium);
  --border-radius: 12px;
}
.pos-more__trigger:hover {
  --color: var(--ion-text-color);
}
@media (pointer: coarse) {
  .pos-more__trigger {
    min-width: 44px;
    min-height: 44px;
  }
}
.pos-more__menu {
  min-width: 13rem;
  padding: 0.3rem;
}
.pos-more__menu ion-item {
  --border-radius: 10px;
  --min-height: 44px;
}
</style>
