<script setup lang="ts">
import type { Route } from '../operations';

defineProps<{
  diagnostic: { route?: Route; available: boolean };
}>();
</script>

<template>
  <template v-if="diagnostic.available || diagnostic.route === 'own'">
    <dt>{{ $t('verifactu.settings.route') }}</dt>
    <dd>{{ diagnostic.route === 'own' ? $t('verifactu.config.own') : $t('verifactu.config.erplora') }}</dd>
  </template>
</template>
