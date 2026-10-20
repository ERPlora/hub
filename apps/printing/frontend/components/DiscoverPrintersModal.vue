<script setup lang="ts">
// «Search printers» (PRINTING-F02; the old «Printers on the network»): on opening, inside the app, it asks
// the device what printers it reaches (lib/discovery.ts) and lists them — name, connection and address —,
// each with «Add» (the page opens «New printer» with it filled in) or «Already added». It says why it found
// nothing: a browser cannot look, the device denied the permission, the app is not linked to this business,
// the scan failed, or nothing answered, with «Search again» where searching again can help. «Add by its
// address» is always there: the way in when the scan cannot see the printer (hub#1924).
import { EmptyState, FormModal, InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSpinner } from '@ionic/vue';
import { shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { type DiscoveryResult, discoverPrinters, nativeInvoke, type PrinterDraft } from '../lib/discovery';
import { printerAddress } from '../lib/format';

const props = defineProps<{ known: readonly string[] }>();
const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ add: [draft: PrinterDraft]; manual: [] }>();

const t = useT();
const searching = shallowRef(false);
const result = shallowRef<DiscoveryResult | null>(null);

async function search(): Promise<void> {
  searching.value = true;
  try {
    result.value = await discoverPrinters(nativeInvoke(), props.known);
  } finally {
    searching.value = false;
  }
}

watch(
  open,
  (now) => {
    if (!now) return;
    result.value = null;
    void search();
  },
  { immediate: true },
);

/** Searching again helps unless this is a browser. */
const canSearchAgain = (r: DiscoveryResult | null) => !!r && r.kind !== 'browser';
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="printing-discover"
    :title="$t('printing.discover.title')"
    :submit-label="$t('printing.discover.manual')"
    :cancel-label="$t('printing.discover.close')"
    @submit="emit('manual')"
  >
    <div class="printing-discover">
      <p
        v-if="searching"
        class="printing-discover__searching"
        data-testid="printing-discover-searching"
      >
        <ion-spinner
          name="crescent"
          aria-hidden="true"
        />
        <span>{{ $t('printing.discover.searching') }}</span>
      </p>
      <template v-else-if="result">
        <InlineFeedback
          v-if="result.kind === 'browser'"
          tone="info"
          icon="information-circle-outline"
          data-testid="printing-discover-browser"
        >
          {{ $t('printing.discover.browser') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="result.kind === 'denied'"
          tone="warning"
          icon="warning-outline"
          data-testid="printing-discover-denied"
        >
          {{ $t('printing.discover.denied') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="result.kind === 'unlinked'"
          tone="warning"
          icon="warning-outline"
          data-testid="printing-discover-unlinked"
        >
          {{ $t('printing.discover.unlinked') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="result.kind === 'failed'"
          tone="danger"
          icon="cloud-offline-outline"
          data-testid="printing-discover-failed"
        >
          {{ $t('printing.discover.failed') }}
        </InlineFeedback>
        <EmptyState
          v-else-if="result.printers.length === 0"
          data-testid="printing-discover-empty"
          icon="search-outline"
          :heading="$t('printing.discover.empty')"
        />
        <ion-list
          v-else
          lines="full"
          class="printing-discover__list"
        >
          <ion-item
            v-for="(found, index) in result.printers"
            :key="found.id"
            data-testid="printing-discover-row"
          >
            <ion-label class="ion-text-wrap">
              <h3>{{ found.name }}</h3>
              <p>{{ t(`printing.kind.${found.draft.kind}`) }} · {{ printerAddress(found.draft) }}</p>
            </ion-label>
            <ion-note
              v-if="found.added"
              slot="end"
              :data-testid="`printing-discover-row-${index}-added`"
            >
              {{ $t('printing.discover.added') }}
            </ion-note>
            <ion-button
              v-else
              slot="end"
              size="small"
              fill="outline"
              :data-testid="`printing-discover-row-${index}-add`"
              @click="emit('add', found.draft)"
            >
              {{ $t('printing.discover.add') }}
            </ion-button>
          </ion-item>
        </ion-list>
        <ion-button
          v-if="canSearchAgain(result)"
          fill="clear"
          size="small"
          class="printing-discover__again"
          data-testid="printing-discover-again"
          @click="search()"
        >
          {{ $t('printing.discover.again') }}
        </ion-button>
      </template>
    </div>
  </FormModal>
</template>

<style scoped>
.printing-discover {
  display: grid;
  gap: 0.75rem;
}
.printing-discover__searching {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}
.printing-discover__list {
  padding: 0;
}
.printing-discover__again {
  justify-self: start;
}
</style>
