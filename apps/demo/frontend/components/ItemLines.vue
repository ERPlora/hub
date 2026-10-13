<script lang="ts">
import type { OutputOf } from '@erplora/ui/sdk';

/** A line as the detail shows it: `pending` marks one laid by an optimistic overlay. */
export type ShownLine = OutputOf<'demo.item.detail'>['lines'][number] & { pending?: boolean };
</script>

<script setup lang="ts">
// The lines of an item, in the server's order. A provisional line (added optimistically, not yet
// confirmed) is faded and says it is being saved; the server's result replaces it.
import { IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';

defineProps<{ lines: ShownLine[] }>();
</script>

<template>
  <ion-list
    v-if="lines.length"
    lines="full"
  >
    <ion-item
      v-for="line in lines"
      :key="line.id"
      data-testid="demo-line"
      :class="{ 'demo-line--pending': line.pending }"
      :aria-busy="line.pending ? 'true' : 'false'"
    >
      <ion-label>
        <span data-testid="demo-line-text">{{ line.text }}</span>
        <p
          v-if="line.pending"
          data-testid="demo-line-pending"
        >
          {{ $t('demo.detail.pending') }}
        </p>
      </ion-label>
      <ion-note
        slot="end"
        data-testid="demo-line-qty"
      >
        × {{ $n(Number(line.qty)) }}
      </ion-note>
    </ion-item>
  </ion-list>
  <p
    v-else
    class="ion-padding-horizontal"
    data-testid="demo-lines-empty"
  >
    <ion-note>{{ $t('demo.detail.noLines') }}</ion-note>
  </p>
</template>

<style scoped>
.demo-line--pending {
  opacity: 0.55;
}
</style>
