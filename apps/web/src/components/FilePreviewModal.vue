<!--
  FilePreviewModal — visor de ficheros de `/files` (ADR-0164).

  Antes, «abrir» un fichero lo descargaba y lo lanzaba a una pestaña del navegador: se salía del
  Hub y en Hub Local (Tauri) ni siquiera hay pestañas. Ahora se previsualiza DENTRO, en un modal
  grande, con un visor por tipo:

    imagen · PDF · hoja de cálculo (xlsx/xlsm/csv/tsv) · Word (docx) · texto/log/código · JSON ·
    vídeo · audio · y un estado explícito «no se puede previsualizar» con descarga.

  Dos restricciones mandan en el diseño:
  1. La CSP del Hub Local prohíbe `frame-src`/`object-src` → NADA de `<iframe>`/`<object>`:
     el PDF se pinta en `<canvas>` (pdf.js) y el .docx se convierte a HTML y se sanea.
  2. Los bytes SIEMPRE los sirve el runtime (`lib/media.fetchMediaBytes`), que es quien lee el
     disco o pide a S3 vía Cloud. El navegador nunca toca el almacenamiento (ADR-0047).

  Los parsers pesados viven en `lib/file-preview-loaders` y se importan perezosamente: abrir un
  `.log` no descarga pdf.js.
-->
<template>
  <ion-modal class="file-preview-modal" :is-open="open" @didDismiss="emit('close')">
    <ion-header>
      <ion-toolbar>
        <ion-title class="preview-title">{{ file?.name ?? '' }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            v-if="zoomable"
            data-test="preview-zoom-out"
            :aria-label="t('files.previewZoomOut')"
            :title="t('files.previewZoomOut')"
            @click="zoomBy(-0.25)"
          >
            <HubIcon name="remove-outline" />
          </ion-button>
          <ion-button
            v-if="zoomable"
            data-test="preview-zoom-in"
            :aria-label="t('files.previewZoomIn')"
            :title="t('files.previewZoomIn')"
            @click="zoomBy(0.25)"
          >
            <HubIcon name="add-outline" />
          </ion-button>
          <ion-button
            data-test="preview-download"
            :aria-label="t('files.download')"
            :title="t('files.download')"
            @click="emit('download')"
          >
            <HubIcon name="download-outline" />
          </ion-button>
          <ion-button
            data-test="preview-close"
            :aria-label="t('files.close')"
            :title="t('files.close')"
            @click="emit('close')"
          >
            <HubIcon name="close-outline" />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>

    <ion-content class="preview-content">
      <div v-if="loading" class="preview-loading">
        <ion-spinner name="crescent" />
      </div>

      <ok-inline-feedback
        v-else-if="errored"
        class="preview-error"
        tone="danger"
        icon="cloud-offline-outline"
        :heading="t('files.previewErrorTitle')"
      >
        {{ t('files.previewErrorBody') }}
      </ok-inline-feedback>

      <ok-empty-state
        v-else-if="kind === 'none'"
        class="preview-unsupported"
        icon="document-outline"
        :heading="t('files.previewUnsupportedTitle')"
        :text="t('files.previewUnsupportedBody')"
      >
        <ion-button slot="actions" @click="emit('download')">{{ t('files.download') }}</ion-button>
      </ok-empty-state>

      <img
        v-else-if="kind === 'image'"
        class="preview-image"
        :src="objectUrl"
        :alt="file?.name ?? ''"
        :style="{ transform: `scale(${zoom})` }"
      />

      <video v-else-if="kind === 'video'" class="preview-media" :src="objectUrl" controls />

      <audio v-else-if="kind === 'audio'" class="preview-media" :src="objectUrl" controls />

      <div v-else-if="kind === 'pdf'" class="preview-pdf">
        <div ref="pdfHost" class="preview-pdf-pages"></div>
        <p v-if="pdfTruncated" class="preview-note">
          {{ t('files.previewPdfTruncated', { shown: PDF_PAGE_LIMIT, total: pdfPages }) }}
        </p>
      </div>

      <div v-else-if="kind === 'sheet'" class="preview-sheet">
        <div v-if="sheets.length > 1" class="preview-sheet-tabs" role="tablist">
          <button
            v-for="(sheet, index) in sheets"
            :key="sheet.name"
            type="button"
            role="tab"
            class="preview-sheet-tab"
            :class="{ active: index === activeSheet }"
            :aria-selected="index === activeSheet"
            @click="activeSheet = index"
          >
            {{ sheet.name }}
          </button>
        </div>
        <ok-data-table ref="tableEl" class="preview-table"></ok-data-table>
      </div>

      <!-- eslint-disable-next-line vue/no-v-html -- saneado con allowlist en `sanitizeDocumentHtml` -->
      <div v-else-if="kind === 'doc'" class="preview-document" v-html="docHtml"></div>

      <ok-json-viewer v-else-if="kind === 'json'" ref="jsonEl" class="preview-json"></ok-json-viewer>

      <ok-code v-else-if="kind === 'text'" ref="codeEl" class="preview-code"></ok-code>
    </ion-content>
  </ion-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonModal,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonButtons,
  IonButton,
  IonContent,
  IonSpinner,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { decodeText, mimeTypeFor, previewKindFor, type PreviewKind } from '../lib/file-preview';
import { loadDocx, loadSheet, renderPdf, type PreviewSheet } from '../lib/file-preview-loaders';
import { fetchMediaBytes } from '../lib/media';
import type { MediaFile } from '../lib/media';

/** Tope de páginas pintadas de una vez: un PDF largo llenaría la memoria de la pestaña. */
const PDF_PAGE_LIMIT = 30;

const props = defineProps<{ file: MediaFile | null; open: boolean }>();
const emit = defineEmits<{ close: []; download: [] }>();
const { t } = useI18n();

const kind = computed<PreviewKind>(() =>
  props.file ? previewKindFor(props.file.name, props.file.ext) : 'none',
);
/** Solo la imagen y el PDF tienen zoom; en el resto los botones estorban. */
const zoomable = computed(() => kind.value === 'image' || kind.value === 'pdf');

const loading = ref(false);
const errored = ref(false);
const objectUrl = ref('');
const docHtml = ref('');
const sheets = ref<PreviewSheet[]>([]);
const activeSheet = ref(0);
const zoom = ref(1);
const pdfPages = ref(0);
const pdfTruncated = computed(() => pdfPages.value > PDF_PAGE_LIMIT);

const pdfHost = useTemplateRef<HTMLElement>('pdfHost');
const codeEl = useTemplateRef<HTMLElement & { code: string; language: string }>('codeEl');
const jsonEl = useTemplateRef<HTMLElement & { data: unknown }>('jsonEl');
const tableEl = useTemplateRef<
  HTMLElement & { columns: unknown[]; rows: Record<string, unknown>[]; paginate: boolean }
>('tableEl');

// Los bytes del fichero abierto: se guardan para poder repintar el PDF al hacer zoom sin volver
// a pedirlos al runtime.
let bytes: ArrayBuffer | null = null;
// Ticket de la carga en curso. Si abres otro fichero antes de que llegue el anterior, la
// respuesta vieja se descarta en vez de pisar lo que ya se está viendo.
let ticket = 0;

function releaseObjectUrl(): void {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = '';
  }
}

function reset(): void {
  releaseObjectUrl();
  bytes = null;
  errored.value = false;
  loading.value = false;
  docHtml.value = '';
  sheets.value = [];
  activeSheet.value = 0;
  zoom.value = 1;
  pdfPages.value = 0;
}

/** Empuja el contenido a los Web Components (props de objeto: asignación imperativa por ref). */
async function applySheet(): Promise<void> {
  await nextTick();
  const element = tableEl.value;
  const sheet = sheets.value[activeSheet.value];
  if (!element || !sheet) return;
  // La primera fila del fichero es la cabecera; el resto, los datos.
  const [header = [], ...body] = sheet.rows;
  element.columns = header.map((label, index) => ({ key: `c${index}`, header: label }));
  element.rows = body.map((row) => Object.fromEntries(row.map((cell, index) => [`c${index}`, cell])));
}

async function paintPdf(): Promise<void> {
  await nextTick();
  if (!pdfHost.value || !bytes) return;
  pdfPages.value = await renderPdf(bytes, pdfHost.value, {
    scale: zoom.value,
    maxPages: PDF_PAGE_LIMIT,
  });
}

async function present(mine: number): Promise<void> {
  if (!bytes || !props.file) return;
  switch (kind.value) {
    case 'image':
    case 'video':
    case 'audio': {
      const type = mimeTypeFor(props.file.name, props.file.ext);
      objectUrl.value = URL.createObjectURL(new Blob([bytes], { type }));
      break;
    }
    case 'pdf':
      await paintPdf();
      break;
    case 'sheet':
      sheets.value = (await loadSheet(bytes, props.file.name)).sheets;
      if (mine !== ticket) return;
      await applySheet();
      break;
    case 'doc':
      docHtml.value = await loadDocx(bytes);
      break;
    case 'json': {
      const parsed = JSON.parse(decodeText(bytes));
      await nextTick();
      if (jsonEl.value) jsonEl.value.data = parsed;
      break;
    }
    case 'text': {
      const text = decodeText(bytes);
      await nextTick();
      if (codeEl.value) codeEl.value.code = text;
      break;
    }
    default:
      break;
  }
}

async function load(): Promise<void> {
  reset();
  const file = props.file;
  // `none` no descarga nada: pedir megabytes para enseñar «no se puede previsualizar» es tirar
  // datos del cliente (y en Hub Cloud, ancho de banda del hub).
  if (!props.open || !file || kind.value === 'none') return;

  const mine = ++ticket;
  loading.value = true;
  const loaded = await fetchMediaBytes(file);
  if (mine !== ticket) return;
  loading.value = false;
  if (!loaded) {
    errored.value = true;
    return;
  }
  bytes = loaded;
  try {
    await present(mine);
  } catch {
    if (mine === ticket) errored.value = true;
  }
}

function zoomBy(delta: number): void {
  zoom.value = Math.min(4, Math.max(0.25, Math.round((zoom.value + delta) * 100) / 100));
  if (kind.value === 'pdf') void paintPdf();
}

watch(() => [props.open, props.file] as const, () => void load(), { immediate: true });
watch(activeSheet, () => void applySheet());
onBeforeUnmount(() => {
  ticket += 1;
  releaseObjectUrl();
});
</script>

<style scoped>
/* Modal GRANDE: el visor necesita superficie. En escritorio deja un marco alrededor; en móvil
   ocupa la pantalla entera. */
.file-preview-modal {
  --width: 96vw;
  --height: 94vh;
  --max-width: 1400px;
  --border-radius: 12px;
}
@media (max-width: 768px) {
  .file-preview-modal {
    --width: 100vw;
    --height: 100vh;
    --border-radius: 0;
  }
}

.preview-title {
  /* Un nombre largo no debe empujar los botones fuera de la barra. */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-content {
  --padding-start: 1rem;
  --padding-end: 1rem;
  --padding-top: 1rem;
  --padding-bottom: 1rem;
  --background: var(--ion-color-step-50, #f7f8fa);
}

.preview-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
}

.preview-image {
  display: block;
  margin: 0 auto;
  max-width: 100%;
  transform-origin: top center;
}

.preview-media {
  display: block;
  margin: 0 auto;
  max-width: 100%;
}

.preview-pdf-pages {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}
.preview-pdf-pages :deep(canvas) {
  max-width: 100%;
  height: auto;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.18);
  background: #fff;
}
.preview-note {
  margin-top: 1rem;
  text-align: center;
  color: var(--ion-color-medium, #92949c);
  font-size: 0.85rem;
}

.preview-sheet-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}
.preview-sheet-tab {
  padding: 0.35rem 0.9rem;
  border: 1px solid var(--ion-border-color, #e4e7ec);
  border-radius: 999px;
  background: var(--ion-background-color, #fff);
  color: var(--ion-text-color, #1f2933);
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}
.preview-sheet-tab.active {
  background: var(--ion-color-primary, #0091ce);
  border-color: var(--ion-color-primary, #0091ce);
  color: var(--ion-color-primary-contrast, #fff);
}

/* El documento de Word se pinta como papel, no como una vista de datos. */
.preview-document {
  max-width: 820px;
  margin: 0 auto;
  padding: 2.5rem 3rem;
  background: var(--ion-background-color, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.12);
  line-height: 1.6;
}
.preview-document :deep(img) {
  max-width: 100%;
  height: auto;
}
.preview-document :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
}
.preview-document :deep(td),
.preview-document :deep(th) {
  border: 1px solid var(--ion-border-color, #e4e7ec);
  padding: 0.4rem 0.6rem;
}
</style>
