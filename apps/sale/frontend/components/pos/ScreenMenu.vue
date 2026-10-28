<script setup lang="ts">
// The ⋮ SCREEN menu (not a sale menu) at the end of the category strip: its one item puts the page on
// the browser's full screen, or takes it off (the whole page: the sheets live in the app's root). The label follows the real state (the toggle, Esc, F11),
// never a local guess. Where the device cannot (an iPhone's Safari) there is no menu at all. Anchored
// under its button; a tap anywhere else, Escape or Android's Back closes it.
import { HubIcon } from '@erplora/ui/shell';
import { onBeforeUnmount, shallowRef } from 'vue';

import { useSystemBack } from '../../composables/pos/useSystemBack';
import { isActive, isCapable, onChange, toggle } from '../../lib/fullscreen';

const open = shallowRef(false);
useSystemBack(open, () => (open.value = false));
const capable = isCapable();
const active = shallowRef(isActive());
const stop = onChange(() => (active.value = isActive()));
onBeforeUnmount(stop);

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
    <button
      type="button"
      class="pos-more__trigger"
      data-testid="pos-screen-menu"
      :aria-label="$t('sale.pos.screenMenu')"
      :title="$t('sale.pos.screenMenu')"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      @click="open = !open"
    >
      <HubIcon name="ion:ellipsis-vertical" />
    </button>
    <template v-if="open">
      <div
        class="pos-more__scrim"
        data-testid="pos-screen-menu-scrim"
        @click="open = false"
      />
      <div
        class="pos-more__menu"
        role="menu"
        data-testid="pos-screen-menu-list"
        @keydown.esc="open = false"
      >
        <button
          type="button"
          role="menuitem"
          data-testid="pos-fullscreen"
          @click="choose"
        >
          <HubIcon name="ion:chevron-expand-outline" />
          {{ active ? $t('sale.pos.exitFullscreen') : $t('sale.pos.fullscreen') }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pos-more {
  position: relative;
  flex: none;
}
.pos-more__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.6rem;
  height: 3.65rem;
  font-size: 1.2rem;
  color: var(--ion-color-medium, #8b897f);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
.pos-more__trigger:hover {
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-color-light, #f2f1ed);
}
.pos-more__scrim {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: transparent;
}
.pos-more__menu {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  z-index: 31;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 13rem;
  padding: 0.3rem;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-background-color, #fff);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
}
.pos-more__menu button {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.7rem;
  font: inherit;
  font-size: 0.92rem;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  border-radius: 10px;
  cursor: pointer;
}
.pos-more__menu button:hover {
  background: var(--ion-color-light, #f2f1ed);
}
.pos-more__menu :deep(ion-icon) {
  font-size: 1.15rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
