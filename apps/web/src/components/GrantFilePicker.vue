<template>
  <div class="grant-file-picker">
    <!-- El input nativo lleva el `data-testid` porque es lo que un e2e rellena; el botón es el
         disfraz, no el control. -->
    <input
      ref="input"
      type="file"
      class="grant-file-input"
      :accept="accept"
      :data-testid="testid"
      @change="onChange"
    />
    <ion-button expand="block" fill="outline" @click="input?.click()">
      <HubIcon slot="start" name="document-attach-outline" />
      {{ label }}
    </ion-button>
  </div>
</template>

<script setup lang="ts">
/**
 * **Adjuntar UN documento del otorgamiento** (hub#1293).
 *
 * La pantalla del otorgamiento pide hasta cuatro ficheros —el modelo firmado, la copia del
 * documento de identidad, la muestra de firma y el justificante de representación— y cada uno
 * llevaba el mismo trío: un `<input type="file">` escondido, un botón que lo dispara y el nombre
 * del fichero elegido. Cuatro copias de eso son cuatro sitios donde el `accept` del input se puede
 * quedar desparejado del botón que dice qué se acepta.
 *
 * Emite `picked` con el `File` o con **`null`** cuando el diálogo se cerró sin elegir: sin ese
 * `null`, quitar un adjunto sería imposible y se acabaría enviando el fichero anterior bajo un
 * botón que ya no lo nombra.
 *
 * `fill="outline"` aquí SÍ pinta: es un `ion-button`, no un control de formulario — donde es un
 * no-op es en `ion-input`/`ion-select`/`ion-textarea` en modo `ios` (ADR-0143 y su enmienda).
 */
import { ref } from 'vue';
import { IonButton } from '@ionic/vue';
import HubIcon from './HubIcon.vue';

defineProps<{
  /** Lo que dice el botón: normalmente el nombre del fichero elegido, o la invitación a elegirlo. */
  label: string;
  /** Qué tipos ofrece el diálogo del sistema. */
  accept?: string;
  /** El `data-testid` del input, para los e2e. */
  testid?: string;
}>();
const emit = defineEmits<{ (e: 'picked', file: File | null): void }>();

const input = ref<HTMLInputElement | null>(null);

function onChange(event: Event) {
  emit('picked', (event.target as HTMLInputElement).files?.[0] ?? null);
}
</script>

<style scoped>
.grant-file-input {
  display: none;
}
</style>
