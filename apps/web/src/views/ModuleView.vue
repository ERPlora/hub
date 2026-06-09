<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start"><ion-menu-button /></ion-buttons>
        <ion-title>Módulo: {{ moduleId }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <div v-if="status === 'loading'" class="flex items-center gap-2 py-8 opacity-70">
        <ion-spinner name="crescent" /> Cargando módulo…
      </div>
      <p v-else-if="status === 'error'" class="text-[color:var(--ion-color-danger)]">
        No se pudo cargar el módulo.
      </p>
      <!-- El WebComponent (Lit) del módulo se monta aquí en runtime (createElement + append). -->
      <div ref="outlet" v-show="status === 'ready'" />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { inject, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent, IonSpinner,
} from '@ionic/vue';
import { loadMenu, loadComponent, type MenuEntry } from '../lib/module-loader';
import { clientInjectionKey, getClient } from '../lib/runtime';

const route = useRoute();
// Cliente del runtime inyectado en el boot (provide en main.ts); fallback al singleton.
const client = inject(clientInjectionKey) ?? getClient();
const outlet = ref<HTMLDivElement | null>(null);
const status = ref<'loading' | 'ready' | 'error'>('loading');
const moduleId = ref<string>(String(route.params.moduleId ?? ''));

async function mount(id: string): Promise<void> {
  status.value = 'loading';
  try {
    const menu = await loadMenu();
    const entry: MenuEntry | undefined = menu.find((m) => m.moduleId === id) ?? menu[0];
    if (!entry) {
      status.value = 'error';
      return;
    }
    const tag = await loadComponent(entry);
    if (outlet.value) {
      outlet.value.innerHTML = '';
      const el = document.createElement(tag) as HTMLElement & { client?: unknown };
      // Inyecta el cliente del runtime ANTES de append: el WC (Lit) lo recibe en su
      // primer render y lo usa para query/command/eventos. WC → SDK → Rust (ARQUITECTURA.md §7.5).
      el.client = client;
      outlet.value.appendChild(el);
    }
    status.value = 'ready';
  } catch {
    status.value = 'error';
  }
}

onMounted(() => mount(moduleId.value));
watch(
  () => route.params.moduleId,
  (id) => {
    if (id) {
      moduleId.value = String(id);
      void mount(moduleId.value);
    }
  },
);
</script>
