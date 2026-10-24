<script setup lang="ts">
// Files › the preview (BASE-G84; the old hub's FilePreviewModal, HUB_SHELL-F132): a large viewer inside the hub with
// the file's name as its title, «Download» and «Close», and «Zoom in»/«Zoom out» on images and PDFs. Images, audio
// and video load from the hub's own address (`/api/files/raw`, with the session; never the bucket's); a PDF, a text,
// a CSV/TSV or a JSON is fetched through the SDK and drawn here: a PDF with pdf.js (its first 30 pages), a text as
// text (never as markup), a CSV as a table, a JSON tidied. Any other type (a spreadsheet, a Word document) says «No
// preview» and offers the download. A failure to bring or to draw it reads «The file could not be opened».
import { InlineFeedback } from '@erplora/ui/components';
import { fetchFile } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonModal } from '@ionic/vue';
import { computed, nextTick, ref, shallowRef, useTemplateRef, watch } from 'vue';

import { extensionOf, parseTable, PDF_PAGES, rawUrl, TABLE_PREVIEW_ROWS, TEXT_PREVIEW_CHARS } from '../lib/files';
import { useBaseI18n } from '../lib/i18n';
import { renderPdf } from '../lib/pdf';
import type { FileItem } from '../operations';

const props = defineProps<{ file: FileItem | null; open: boolean }>();
const emit = defineEmits<{ close: []; download: [] }>();

const { t } = useBaseI18n();

type State = 'loading' | 'ready' | 'error';
const state = ref<State>('loading');
const text = ref('');
const cut = ref(false);
const rows = ref<string[][]>([]);
const pdfPages = shallowRef<HTMLCanvasElement[]>([]);
const pdfTotal = ref(0);
const zoom = ref(100);
const pdfHost = useTemplateRef<HTMLElement>('pdfHost');
/** The file this load is for: a later one wins, an earlier answer is dropped. */
let loading = 0;

const kind = computed(() => props.file?.preview ?? '');
const inlineUrl = computed(() => (props.file ? rawUrl(props.file.path, true) : ''));
const zoomable = computed(() => kind.value === 'image' || kind.value === 'pdf');

async function load(file: FileItem): Promise<void> {
  const mine = ++loading;
  state.value = 'loading';
  text.value = '';
  cut.value = false;
  rows.value = [];
  pdfPages.value = [];
  zoom.value = 100;
  if (!['pdf', 'text', 'table', 'json'].includes(file.preview)) {
    state.value = 'ready';
    return;
  }
  try {
    const { blob } = await fetchFile(rawUrl(file.path, true), file.content_type);
    if (mine !== loading) return;
    if (file.preview === 'pdf') {
      const drawn = await renderPdf(new Uint8Array(await blob.arrayBuffer()));
      if (mine !== loading) return;
      pdfPages.value = drawn.pages;
      pdfTotal.value = drawn.total;
      cut.value = drawn.total > PDF_PAGES;
    } else {
      const content = await blob.text();
      if (mine !== loading) return;
      if (file.preview === 'table') {
        const separator = extensionOf(file.name) === 'tsv' ? '\t' : ',';
        rows.value = parseTable(content, separator, TABLE_PREVIEW_ROWS + 1);
        cut.value = rows.value.length > TABLE_PREVIEW_ROWS;
        rows.value = rows.value.slice(0, TABLE_PREVIEW_ROWS);
      } else {
        text.value = file.preview === 'json' ? tidyJson(content) : content;
        cut.value = text.value.length > TEXT_PREVIEW_CHARS;
        text.value = text.value.slice(0, TEXT_PREVIEW_CHARS);
      }
    }
    state.value = 'ready';
  } catch (error) {
    if (mine !== loading) return;
    console.error('files: the preview could not be opened', error);
    state.value = 'error';
  }
}

/** A JSON with two-space indents; a broken one, as it is. */
function tidyJson(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

watch(
  () => [props.open, props.file] as const,
  ([open, file]) => {
    if (open && file) void load(file);
  },
  { immediate: true },
);

// The canvases pdf.js drew go into their host once it is on the page.
watch([pdfPages, pdfHost], async () => {
  await nextTick();
  const host = pdfHost.value;
  if (!host) return;
  host.replaceChildren(...pdfPages.value);
});

const scaled = computed(() => ({ width: `${zoom.value}%` }));

function zoomBy(step: number): void {
  zoom.value = Math.min(300, Math.max(25, zoom.value + step));
}

function mediaFailed(): void {
  state.value = 'error';
}
</script>

<template>
  <ion-modal
    class="file-preview"
    :is-open="open"
    data-testid="file-preview"
    @did-dismiss="emit('close')"
  >
    <header class="file-preview-head">
      <h2
        class="file-preview-title"
        data-testid="file-preview-title"
      >
        {{ file?.name ?? '' }}
      </h2>
      <div class="file-preview-actions">
        <ion-button
          v-show="zoomable && state === 'ready'"
          size="small"
          fill="clear"
          data-testid="file-preview-zoom-out"
          @click="zoomBy(-25)"
        >
          {{ t('base.files.preview.zoomOut') }}
        </ion-button>
        <ion-button
          v-show="zoomable && state === 'ready'"
          size="small"
          fill="clear"
          data-testid="file-preview-zoom-in"
          @click="zoomBy(25)"
        >
          {{ t('base.files.preview.zoomIn') }}
        </ion-button>
        <ion-button
          size="small"
          fill="outline"
          data-testid="file-preview-download"
          @click="emit('download')"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ t('base.files.preview.download') }}
        </ion-button>
        <ion-button
          size="small"
          fill="solid"
          data-testid="file-preview-close"
          @click="emit('close')"
        >
          {{ t('base.files.preview.close') }}
        </ion-button>
      </div>
    </header>
    <div class="file-preview-body">
      <div
        v-if="file"
        class="file-preview-stage"
      >
        <p
          v-if="state === 'loading' && kind && !['image', 'audio', 'video'].includes(kind)"
          class="file-preview-muted"
          data-testid="file-preview-loading"
          role="status"
        >
          {{ t('base.files.preview.loading') }}
        </p>
        <InlineFeedback
          v-if="state === 'error'"
          tone="danger"
          data-testid="file-preview-error"
          :heading="t('base.files.preview.error.heading')"
        >
          {{ t('base.files.preview.error.body') }}
        </InlineFeedback>
        <template v-else>
          <InlineFeedback
            v-if="!kind"
            tone="info"
            data-testid="file-preview-none"
            :heading="t('base.files.preview.none.heading')"
          >
            {{ t('base.files.preview.none.body') }}
          </InlineFeedback>
          <img
            v-else-if="kind === 'image'"
            class="file-preview-image"
            data-testid="file-preview-image"
            :src="inlineUrl"
            :alt="file.name"
            :style="scaled"
            @load="state = 'ready'"
            @error="mediaFailed()"
          >
          <audio
            v-else-if="kind === 'audio'"
            controls
            class="file-preview-audio"
            data-testid="file-preview-audio"
            :src="inlineUrl"
            @error="mediaFailed()"
          />
          <video
            v-else-if="kind === 'video'"
            controls
            class="file-preview-video"
            data-testid="file-preview-video"
            :src="inlineUrl"
            @error="mediaFailed()"
          />
          <template v-else-if="state === 'ready'">
            <p
              v-if="cut"
              class="file-preview-muted"
              data-testid="file-preview-cut"
            >
              {{
                kind === 'pdf'
                  ? t('base.files.preview.pdfPages', { shown: PDF_PAGES, total: pdfTotal })
                  : kind === 'table'
                    ? t('base.files.preview.tableCut', { shown: TABLE_PREVIEW_ROWS })
                    : t('base.files.preview.textCut')
              }}
            </p>
            <div
              v-if="kind === 'pdf'"
              ref="pdfHost"
              class="file-preview-pdf"
              data-testid="file-preview-pdf"
              :style="scaled"
            />
            <div
              v-else-if="kind === 'table'"
              class="file-preview-table-wrap"
            >
              <table
                class="file-preview-table"
                data-testid="file-preview-table"
              >
                <thead v-if="rows.length">
                  <tr>
                    <th
                      v-for="(cell, index) in rows[0]"
                      :key="index"
                    >
                      {{ cell }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, index) in rows.slice(1)"
                    :key="index"
                  >
                    <td
                      v-for="(cell, column) in row"
                      :key="column"
                    >
                      {{ cell }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <pre
              v-else
              class="file-preview-text"
              data-testid="file-preview-text"
            >{{ text }}</pre>
          </template>
        </template>
      </div>
    </div>
  </ion-modal>
</template>

<style scoped>
.file-preview {
  --width: min(1100px, 94vw);
  --height: min(860px, 92vh);
}

.file-preview-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
}

.file-preview-title {
  min-width: 0;
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.file-preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.file-preview-body {
  flex: 1;
  overflow: auto;
}

.file-preview-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-height: 100%;
  padding: 16px;
}

.file-preview-muted {
  align-self: stretch;
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.file-preview-image {
  max-width: none;
  height: auto;
  object-fit: contain;
}

.file-preview-audio {
  width: min(560px, 100%);
}

.file-preview-video {
  max-width: 100%;
  max-height: 75vh;
}

.file-preview-pdf {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-preview-pdf :deep(canvas) {
  width: 100%;
  height: auto;
  box-shadow: 0 1px 4px rgb(0 0 0 / 18%);
}

.file-preview-table-wrap {
  align-self: stretch;
  overflow: auto;
}

.file-preview-table {
  border-collapse: collapse;
  font-size: 0.875rem;
}

.file-preview-table th,
.file-preview-table td {
  padding: 6px 10px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  text-align: start;
  white-space: nowrap;
}

.file-preview-table th {
  background: var(--ion-color-light, #f4f5f8);
  font-weight: 600;
}

.file-preview-text {
  align-self: stretch;
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--ion-color-light, #f4f5f8);
  font-size: 0.8125rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
