<script setup lang="ts">
// What other apps know about the customer, at the end of the card (CUSTOMER-F24; the product's
// `customers.detail` slot). Contract (WORKBOOK «CUSTOMER-F24»): an app that wants a block on the
// card ships `apps/<id>/frontend/customer-card/<Block>.vue`, a component with one prop, `customerId`;
// Customers depends on none of them: it finds them here (like main.ts finds every app's routes),
// paints only those of apps that are on in this business, each in its own chunk and frame (a block
// that breaks says so in its place), and tells them nothing but which customer is open.
import { useSession } from '@erplora/ui/shell';
import { type Component, computed, defineAsyncComponent } from 'vue';

import CardBlockBoundary from './CardBlockBoundary.vue';

type Loader = () => Promise<{ default: Component }>;

const props = withDefaults(
  defineProps<{
    customerId: string;
    /** The blocks by file; every app's `customer-card` folder by default (tests pass their own). */
    blocks?: Record<string, Loader>;
  }>(),
  { blocks: () => import.meta.glob<{ default: Component }>('../../../*/frontend/customer-card/*.vue') },
);

const session = useSession();

/** `../../../<app>/frontend/customer-card/<Block>.vue` → `<app>`. */
const appOf = (file: string): string => file.split('/').at(-4) ?? '';

const components = new Map<string, Component>();
function componentOf(file: string): Component {
  let found = components.get(file);
  if (!found) {
    const load = props.blocks[file];
    found = defineAsyncComponent(() => load().then((module) => module.default));
    components.set(file, found);
  }
  return found;
}

const shown = computed(() => {
  const apps = session.me.value?.apps ?? [];
  const on = apps.filter((app) => app.state === 'on').map((app) => app.label);
  return Object.keys(props.blocks)
    .filter((file) => on.includes(appOf(file)))
    .sort((a, b) => on.indexOf(appOf(a)) - on.indexOf(appOf(b)) || a.localeCompare(b))
    .map((file) => ({ file, app: appOf(file), component: componentOf(file) }));
});
</script>

<template>
  <div
    v-if="shown.length"
    class="customer-card-blocks"
    data-testid="customer-card-blocks"
  >
    <section
      v-for="block in shown"
      :key="block.file"
      class="customer-card-blocks__block"
      data-testid="customer-card-block"
      :data-app="block.app"
    >
      <CardBlockBoundary
        :block="block.component"
        :customer-id="customerId"
      />
    </section>
  </div>
</template>

<style scoped>
.customer-card-blocks__block {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: var(--ep-radius-sm, 10px);
  padding: 0.75rem 1rem;
  margin: 0 0 1rem;
}
</style>
