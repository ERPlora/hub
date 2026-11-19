<script setup lang="ts">
import { StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { computed } from 'vue';

import type { ConfigOut } from '../operations';

const props = defineProps<{
  certificate: ConfigOut['own_certificate'];
  testid: string;
}>();

const status = computed<{ tone: StatusPillTone; label: string }>(() => {
  const cert = props.certificate;
  if (!cert.loaded) return { tone: 'neutral', label: 'verifactu.config.notUploaded' };
  if (cert.expires_in_days !== null && cert.expires_in_days < 0) {
    return { tone: 'danger', label: 'verifactu.config.expiredStatus' };
  }
  if (cert.expires_soon) {
    return { tone: 'warning', label: 'verifactu.config.expiringSoon' };
  }
  return { tone: 'success', label: 'verifactu.config.valid' };
});
</script>

<template>
  <StatusPill
    :data-testid="testid"
    :tone="status.tone"
    :label="$t(status.label)"
  />
</template>
