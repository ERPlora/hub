<script setup lang="ts">
import { StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { computed } from 'vue';

import type { ConfigOut } from '../operations';

const props = defineProps<{
  certificate: ConfigOut['own_certificate'];
  testid: string;
}>();

const TONES: Record<ConfigOut['own_certificate']['aeat_proof'], StatusPillTone> = {
  untested: 'neutral',
  accepted: 'success',
  rejected: 'danger',
};

const tone = computed(() => TONES[props.certificate.aeat_proof]);
</script>

<template>
  <StatusPill
    :data-testid="testid"
    :tone="tone"
    :label="$t(`verifactu.config.proof.${certificate.aeat_proof}`)"
  />
</template>
