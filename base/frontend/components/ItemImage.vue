<script setup lang="ts">
// The photo of a product, a service or a set menu (INVENTORY-F32, SERVICE-F34, COMBO-F14): the photo when it has one,
// covering its box, loaded lazily and named by the item; its initials over its colour when it has none or the photo
// does not load (offline, deleted, no longer in the library), never a gap nor a broken image. The box's size and the
// initials' type size are its parent's (a till tile, a list's thumbnail, the form's preview); what the parent lays over
// it (a till tile's warning) goes in the default slot.
import { computed, ref, watch } from 'vue';

import { initials, tileGradient } from '../lib/item-image';

const props = defineProps<{
  /** Where the Hub serves the photo (`image_url`), or `''`/`null`: none. */
  src?: string | null;
  /** The item's name: its photo's text alternative and its initials. */
  name: string;
}>();

/** The current photo could not be loaded. */
const broken = ref(false);
watch(
  () => props.src,
  () => {
    broken.value = false;
  },
);

const shown = computed(() => (props.src && !broken.value ? props.src : ''));
const style = computed(() => (shown.value ? undefined : { background: tileGradient(props.name) }));
</script>

<template>
  <span
    class="item-image"
    :class="{ 'item-image--photo': !!shown }"
    :style="style"
    :data-image="shown ? 'photo' : 'initials'"
  >
    <img
      v-if="shown"
      class="item-image__photo"
      :src="shown"
      :alt="name"
      loading="lazy"
      decoding="async"
      @error="broken = true"
    >
    <span
      v-else
      class="item-image__initials"
      aria-hidden="true"
    >{{ initials(name) }}</span>
    <slot />
  </span>
</template>

<style scoped>
.item-image {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.85);
}
.item-image--photo {
  background: #fff;
}
.item-image__photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.item-image__initials {
  line-height: 1;
  user-select: none;
}
</style>
