<script setup lang="ts">
// The Home's templates card while its load still waits for an app (hub#609): its data comes by itself once the app is
// ready, an app whose setup failed says so, and the load is followed live (`base.import.list`, which re-runs on what the
// apps do), only while this is shown. When it no longer waits for anything, `settled` hands the card how it ended.
import { useLive } from '@erplora/ui/sdk';
import { IonSpinner } from '@ionic/vue';
import { computed, watch } from 'vue';

import { pendingApps } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';
import type { ImportRow } from '../operations';
import '../home.css';

const props = defineProps<{ load: ImportRow }>();
const emit = defineEmits<{ settled: [load: ImportRow] }>();

const { t } = useBaseI18n();
const imports = useLive('base.import.list', {});

const current = computed(() => imports.data.value?.imports.find((row) => row.id === props.load.id) ?? props.load);
const pending = computed(() => pendingApps(current.value.report));

watch(pending, ({ settingUp, failing }) => {
  if (!settingUp.length && !failing.length) emit('settled', current.value);
});
</script>

<template>
  <div aria-live="polite">
    <div
      v-if="pending.settingUp.length"
      data-testid="blueprint-card-pending"
    >
      <h3 class="blueprint-card-heading">
        {{ t('base.blueprintCard.pendingTitle') }}
      </h3>
      <p class="blueprint-card-busy">
        <ion-spinner name="crescent" />
        <span>{{ t('base.blueprintCard.pendingHint', { apps: pending.settingUp.join(', ') }) }}</span>
      </p>
    </div>
    <div
      v-if="pending.failing.length"
      data-testid="blueprint-card-failing"
    >
      <h3 class="blueprint-card-heading">
        {{ t('base.blueprintCard.failingTitle') }}
      </h3>
      <p class="blueprint-card-text">
        {{ t('base.blueprintCard.failingHint', { apps: pending.failing.join(', ') }) }}
      </p>
    </div>
  </div>
</template>
