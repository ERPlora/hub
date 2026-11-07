<script setup lang="ts">
// «Loading…» while what a screen needs is still being read (WORKBOOK «Estados de cada pantalla · Cargando»): a status
// a screen reader reads out, as the table's own «Loading…» is; the dots are decoration. Used where the person would
// otherwise see an empty screen as if there were nothing: above the gallery (hub#950) and in «Which data?» (hub#969).
import { IonSpinner } from '@ionic/vue';
</script>

<template>
  <div
    class="flow-loading"
    role="status"
  >
    <IonSpinner
      name="dots"
      aria-hidden="true"
    /> {{ $t('flow.loading') }}
  </div>
</template>

<style scoped>
.flow-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
