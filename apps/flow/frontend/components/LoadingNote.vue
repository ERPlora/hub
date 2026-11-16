<script setup lang="ts">
// «Loading…» while what a screen needs is still being read (WORKBOOK «Estados de cada pantalla · Cargando»): a status
// a screen reader reads out, as the table's own «Loading…» is; the dots are decoration. Used where the person would
// otherwise see an empty screen as if there were nothing: above the gallery (hub#950) and in «Which data?» (hub#969).
// Ionic's own colour and utility classes, no sheet of its own.
import { IonSpinner, IonText } from '@ionic/vue';
</script>

<template>
  <IonText
    color="medium"
    class="ion-display-flex ion-align-items-center"
    role="status"
  >
    <IonSpinner
      name="dots"
      class="ion-margin-end"
      aria-hidden="true"
    />
    {{ $t('flow.loading') }}
  </IonText>
</template>
