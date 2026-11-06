<script setup lang="ts">
// The cards the apps on put in System › «Usage and plan» (hub#683; the old hub's «Your printer» of «Resources»): base
// follows `base.system.cards` live — an app turned on brings its cards, one turned off takes them away — and mounts each
// card's component of its app (`lib/app-components.ts`), in the server's order. What a card says, and how it says it
// is loading or failing, is its app's: base never learns what is in it. None while the list loads; a card whose
// component its app lacks, or whose component fails to load, is left out and logged, and the others stay; a list that
// cannot be read hides the cards (the old hub's rule: «the unreadable list of apps leaves the card hidden»), while the
// rest of the tab says its own.
import { useLive } from '@erplora/ui/sdk';
import { type Component, computed, defineAsyncComponent, reactive } from 'vue';

import type { SystemCardDef } from '../operations';
import { appComponent } from '../lib/app-components';

const { data, status } = useLive('base.system.cards', {});

/** Each card's component, made once per card and component; `null`: its app has no such component. */
const made = new Map<string, Component | null>();
/** The cards whose component failed to load. */
const failed = reactive(new Set<string>());

function componentOf(card: SystemCardDef): Component | null {
  const id = `${card.key}:${card.component}`;
  if (!made.has(id)) {
    const loader = appComponent(card.app, card.component);
    if (!loader) console.warn(`base: the System card ${card.key} names ${card.component}, which its app does not have`);
    made.set(
      id,
      loader
        ? defineAsyncComponent({
            loader,
            onError(error, _retry, fail) {
              console.warn(`base: the System card ${card.key} could not load its component`, error);
              failed.add(card.key);
              fail();
            },
          })
        : null,
    );
  }
  return made.get(id) ?? null;
}

const cards = computed(() =>
  status.value === 'error'
    ? []
    : (data.value?.cards ?? []).flatMap((card) => {
        const component = componentOf(card);
        return component && !failed.has(card.key) ? [{ key: card.key, component }] : [];
      }),
);
</script>

<template>
  <div
    v-for="card in cards"
    :key="card.key"
    :data-testid="`system-app-card-${card.key}`"
  >
    <component :is="card.component" />
  </div>
</template>
