<!--
  HubIcon — único punto para pintar iconos en el shell del Hub.

  Sustituye a `<ion-icon :icon="…">`. Recibe un `name` (nombre Iconify `ion:` del set del shell,
  p. ej. "save-outline") o, para iconos que trae un módulo, el SVG inline directamente. Lo resuelve
  con lib/icons.ts (SVG horneado en build, offline) y lo pinta dentro de un `<ion-icon>` real, de
  modo que `ion-button`/`ion-item` lo maquetan y colorean igual que un ionicon nativo (color por
  currentColor, tamaño por el slot). Los atributos extra (`slot`, `size`, `color`, `class`…) caen
  por fallthrough al `<ion-icon>` raíz; solo `name` se consume como prop.

  Uso:  <HubIcon name="save-outline" slot="start" />
        <HubIcon :name="kpi.icon" />                 (nombre dinámico)
        <HubIcon :name="entry.nav.icon" size="large" /> (nombre o SVG inline de un módulo)

  TODO(#39): set de iconos del chrome (lucide vía iconify, como Cloud, vs ionicons, como el Hub
  hoy) = DECISIÓN DEL HUMANO. No se unifica el set aquí; el shell sigue con `ion:` (+ alias lucide
  en lib/icons.ts) hasta que el humano fije el set canónico para shells idénticos píxel a píxel.
-->
<script setup lang="ts">
import { computed } from 'vue';
import { IonIcon } from '@ionic/vue';
import { resolveIcon } from '../lib/icons';

const props = defineProps<{ name?: string }>();

const icon = computed(() => resolveIcon(props.name));
</script>

<template>
  <ion-icon :icon="icon" />
</template>
