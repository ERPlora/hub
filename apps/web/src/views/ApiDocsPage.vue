<!--
  ApiDocsPage — documentación de la API pública del Hub (ADR-0057 §4, refinado 2026-06-24).

  El Swagger se renderiza DENTRO de esta vista Vue (no iframe, no URL pública): `swagger-ui-dist`
  (npm) recibe el spec por la opción `spec:`, así que Swagger NUNCA hace su propio fetch sin auth.
  El spec lo pedimos con el fetch AUTENTICADO del web app (lib/api-docs → runtimeHeaders →
  X-Hub-Session); el runtime exige sesión de usuario (interno, no público). El "Try it out" llamará
  a la API real con la API key que el usuario pegue como bearer (correcto: la API key es la
  credencial de la API, no la sesión del usuario).

  Visible para CUALQUIER usuario logueado (verla es inofensivo). La entrada de menú/página la
  controla el toggle de Ajustes ("Mostrar documentación de la API", lib/api-docs.apiDocsEnabled),
  preferencia client-side; la seguridad real es el gate de sesión sobre `openapi.json`.

  Aislamiento de CSS: el CSS de Swagger es pesado pero está prefijado bajo `.swagger-ui` (Swagger
  monta todo dentro de un root `.swagger-ui`), así que no rompe el shell. Lo encerramos además en un
  contenedor con scroll propio (`.api-docs-host`) para que el bloque viva dentro del `ion-content`.
-->
<template>
  <AppPage :title="t('apiDocs.title')">
    <div class="api-docs-wrap">
      <ok-inline-feedback
        tone="info"
        :heading="t('apiDocs.introTitle')"
        icon="information-circle-outline"
      >
        {{ t('apiDocs.introBody') }}
      </ok-inline-feedback>

      <!-- Cargando el spec -->
      <div v-if="loading" class="api-docs-state">
        <ion-spinner name="dots" />
        <span>{{ t('apiDocs.loading') }}</span>
      </div>

      <!-- Error al cargar el spec (sin sesión, runtime caído, etc.) -->
      <ok-inline-feedback
        v-else-if="error"
        tone="danger"
        :heading="t('apiDocs.errorTitle')"
        icon="alert-circle-outline"
      >
        {{ error }}
        <ion-button slot="actions" size="small" fill="outline" @click="loadSpec">
          {{ t('apiDocs.retry') }}
        </ion-button>
      </ok-inline-feedback>

      <!-- Host de Swagger UI: se monta imperativamente sobre `swaggerEl`. -->
      <div v-show="!loading && !error" ref="swaggerEl" class="api-docs-host"></div>
    </div>
  </AppPage>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonSpinner } from '@ionic/vue';
import AppPage from '../components/AppPage.vue';
import { fetchOpenApiSpec } from '../lib/api-docs';
// CSS global de Swagger UI (prefijado bajo `.swagger-ui`). Importado por su efecto secundario.
import 'swagger-ui-dist/swagger-ui.css';
// Bundle ES de Swagger UI. Default export = `SwaggerUIBundle` (firma declarada en env.d.ts).
import SwaggerUIBundle from 'swagger-ui-dist/swagger-ui-es-bundle.js';

const { t } = useI18n();

const swaggerEl = ref<HTMLElement | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
let instance: { unmount?: () => void } | null = null;

async function loadSpec(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    instance?.unmount?.();
  } catch {
    /* noop */
  }
  instance = null;
  swaggerEl.value?.replaceChildren();
  try {
    // 1) Pedimos el spec con el fetch autenticado (X-Hub-Session). Swagger NO lo descarga: se lo
    //    damos ya resuelto por `spec:` para no perder la auth (no hay `url:`).
    const spec = await fetchOpenApiSpec();
    loading.value = false;
    // 2) Montamos Swagger sobre el host. `domNode` (no `dom_id`) para no acoplar a un id global.
    //    `tryItOutEnabled`: el "Try it out" pega a la API real con la API key como bearer.
    if (swaggerEl.value) {
      instance = SwaggerUIBundle({
        domNode: swaggerEl.value,
        spec,
        deepLinking: true,
        docExpansion: 'list',
        tryItOutEnabled: true,
      });
    }
  } catch (e) {
    loading.value = false;
    console.warn('OpenAPI spec could not be loaded', e);
    error.value = t('apiDocs.errorBody');
  }
}

onMounted(loadSpec);

onBeforeUnmount(() => {
  // Swagger UI no siempre expone unmount; si existe, lo llamamos para soltar listeners.
  try {
    instance?.unmount?.();
  } catch {
    /* noop */
  }
  instance = null;
});
</script>

<style scoped>
.api-docs-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* Contenedor del Swagger: ocupa el resto del alto y scrollea por dentro (la cabecera/feedback
   queda fija arriba). El CSS de Swagger vive bajo `.swagger-ui`, así que no se sale de aquí. */
.api-docs-host {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  border-radius: 10px;
  background: var(--ion-background-color, #fff);
}

/* Suaviza el margen superior que Swagger pone en su barra de info para integrarlo en la tarjeta. */
.api-docs-host :deep(.swagger-ui .info) {
  margin: 1rem 0;
}

/* En móvil los paths de endpoint son largos y Swagger los rompe en mitad de segmento con
   `word-break:break-word`. Forzamos `break-all` para que el corte ocurra en cualquier carácter
   (más predecible) y el path sea legible en pantallas estrechas. */
.api-docs-host :deep(.swagger-ui .opblock-summary-path) {
  word-break: break-all;
}

.api-docs-state {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.5rem 0;
  opacity: 0.75;
}
</style>
