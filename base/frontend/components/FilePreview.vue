<script setup lang="ts">
// Images, audio and video load from the hub's own address (`/api/files/raw`, with the session), never from the bucket.
// Other previewable files are fetched through the SDK and drawn here, never painted as HTML: a PDF with pdf.js (its
// first 30 pages), a text as text, a CSV or each sheet of a spreadsheet as a table, a JSON as a tree that folds and a
// Word document as its formatted text. A spreadsheet or document over `OFFICE_PREVIEW_MAX_BYTES` is never fetched.
import { InlineFeedback } from '@erplora/ui/components';
import { fetchFile } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonModal } from '@ionic/vue';
import { computed, nextTick, ref, shallowRef, useTemplateRef, watch } from 'vue';

import {
  cellText,
  extensionOf,
  formatSize,
  OFFICE_PREVIEW_MAX_BYTES,
  parseTable,
  PDF_PAGES,
  type PreviewSheet,
  PreviewTooLarge,
  rawUrl,
  sheetRows,
  TABLE_PREVIEW_ROWS,
  TEXT_PREVIEW_CHARS,
  viewerOf,
} from '../lib/files';
import { useBaseI18n } from '../lib/i18n';
import { type DocumentNode, readDocument, readSheets } from '../lib/office';
import { renderPdf } from '../lib/pdf';
import type { FileItem } from '../operations';
import FileDocument from './FileDocument.vue';
import FileJsonTree from './FileJsonTree.vue';
import FileSheets from './FileSheets.vue';

const props = defineProps<{ file: FileItem | null; open: boolean }>();
const emit = defineEmits<{ close: []; download: [] }>();

const { t, locale } = useBaseI18n();

/** `error`: the file did not arrive; `damaged`: it arrived and could not be read; `tooLarge`: not read, too big. */
type State = 'loading' | 'ready' | 'error' | 'damaged' | 'tooLarge';
/** What the preview fetches and draws itself (the rest loads from its address, or is not shown). */
const FETCHED = ['pdf', 'text', 'table', 'json', 'sheet', 'document'];
/** What it reads with a library in the page, and refuses past `OFFICE_PREVIEW_MAX_BYTES`. */
const OFFICE = ['sheet', 'document'];
const state = ref<State>('loading');
const text = ref('');
const cut = ref(false);
const sheets = shallowRef<PreviewSheet[]>([]);
/** The JSON read, or `null` while none (or a broken one, shown as text). */
const json = shallowRef<{ value: unknown } | null>(null);
const brokenJson = ref(false);
const documentNodes = shallowRef<DocumentNode[]>([]);
const pdfPages = shallowRef<HTMLCanvasElement[]>([]);
const pdfTotal = ref(0);
const zoom = ref(100);
/** The image's own size once it loaded: the fit is worked out from it. */
const natural = ref<{ width: number; height: number } | null>(null);
const pdfHost = useTemplateRef<HTMLElement>('pdfHost');
/** The file this load is for: a later one wins, an earlier answer is dropped. */
let loading = 0;

const kind = computed(() => (props.file ? viewerOf(props.file) : ''));
const maxOffice = computed(() => formatSize(OFFICE_PREVIEW_MAX_BYTES, locale.value));
const inlineUrl = computed(() => (props.file ? rawUrl(props.file.path, true) : ''));
const zoomable = computed(() => kind.value === 'image' || kind.value === 'pdf');

async function load(file: FileItem): Promise<void> {
  const mine = ++loading;
  state.value = 'loading';
  text.value = '';
  cut.value = false;
  sheets.value = [];
  json.value = null;
  brokenJson.value = false;
  documentNodes.value = [];
  pdfPages.value = [];
  zoom.value = 100;
  natural.value = null;
  const viewer = viewerOf(file);
  if (!FETCHED.includes(viewer)) {
    state.value = 'ready';
    return;
  }
  if (OFFICE.includes(viewer) && file.size > OFFICE_PREVIEW_MAX_BYTES) {
    state.value = 'tooLarge';
    return;
  }
  let blob: Blob;
  try {
    ({ blob } = await fetchFile(rawUrl(file.path, true), file.content_type));
  } catch (error) {
    if (mine !== loading) return;
    console.error('files: the preview could not be opened', error);
    state.value = 'error';
    return;
  }
  if (mine !== loading) return;
  try {
    await draw(viewer, file, blob, mine);
    if (mine === loading) state.value = 'ready';
  } catch (error) {
    if (mine !== loading) return;
    console.error('files: the preview could not read the file', error);
    state.value = error instanceof PreviewTooLarge ? 'tooLarge' : 'damaged';
  }
}

/** Reads `blob` as `viewer` shows it, unless a later file took over (`mine`). */
async function draw(viewer: string, file: FileItem, blob: Blob, mine: number): Promise<void> {
  if (viewer === 'pdf' || OFFICE.includes(viewer)) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (viewer === 'pdf') {
      const drawn = await renderPdf(bytes);
      if (mine !== loading) return;
      pdfPages.value = drawn.pages;
      pdfTotal.value = drawn.total;
      cut.value = drawn.total > PDF_PAGES;
    } else if (viewer === 'sheet') {
      const words = { yes: t('base.files.preview.yes'), no: t('base.files.preview.no') };
      const read = await readSheets(bytes);
      if (mine !== loading) return;
      sheets.value = read.map((sheet) => {
        const shown = sheetRows(sheet.rows);
        return { name: sheet.name, cut: shown.cut, rows: shown.rows.map((row) => row.map((cell) => cellText(cell, locale.value, words))) };
      });
    } else {
      const nodes = await readDocument(bytes);
      if (mine !== loading) return;
      documentNodes.value = nodes;
    }
    return;
  }
  const content = await blob.text();
  if (mine !== loading) return;
  if (viewer === 'table') {
    const separator = extensionOf(file.name) === 'tsv' ? '\t' : ',';
    sheets.value = [{ name: file.name, ...sheetRows(parseTable(content, separator, TABLE_PREVIEW_ROWS + 1)) }];
    return;
  }
  if (viewer === 'json') {
    try {
      json.value = { value: JSON.parse(content) as unknown };
      return;
    } catch {
      // A broken JSON is shown as it is, saying so.
      brokenJson.value = true;
    }
  }
  cut.value = content.length > TEXT_PREVIEW_CHARS;
  text.value = content.slice(0, TEXT_PREVIEW_CHARS);
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

/** A PDF fits the viewer's width (as PDF viewers open); the zoom is a share of it. */
const pdfScaled = computed(() => ({ width: `${zoom.value}%` }));
/** An image fits the viewer as Drive's does: never larger than itself, nor than the stage's width or height (16 px of
 *  padding a side, `cqw`/`cqh` of the viewer's body); the zoom multiplies that. */
const imageScaled = computed(() => {
  const size = natural.value;
  if (!size?.width || !size.height) return {};
  const fit = `min(${size.width}px, 100cqw - 32px, (100cqh - 32px) * ${size.width / size.height})`;
  return { width: `calc(${fit} * ${zoom.value / 100})`, maxWidth: 'none' };
});

function imageLoaded(event: Event): void {
  const image = event.target as HTMLImageElement;
  natural.value = { width: image.naturalWidth, height: image.naturalHeight };
  state.value = 'ready';
}

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
        <InlineFeedback
          v-else-if="state === 'damaged'"
          tone="danger"
          data-testid="file-preview-damaged"
          :heading="t('base.files.preview.damaged.heading')"
        >
          {{ t('base.files.preview.damaged.body') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="state === 'tooLarge'"
          tone="info"
          data-testid="file-preview-too-large"
          :heading="t('base.files.preview.tooLarge.heading')"
        >
          {{ t('base.files.preview.tooLarge.body', { size: maxOffice }) }}
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
            :style="imageScaled"
            @load="imageLoaded($event)"
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
                  : t('base.files.preview.textCut')
              }}
            </p>
            <p
              v-if="brokenJson"
              class="file-preview-muted"
              data-testid="file-preview-json-broken"
            >
              {{ t('base.files.preview.json.broken') }}
            </p>
            <div
              v-if="kind === 'pdf'"
              ref="pdfHost"
              class="file-preview-pdf"
              data-testid="file-preview-pdf"
              :style="pdfScaled"
            />
            <FileSheets
              v-else-if="kind === 'table' || kind === 'sheet'"
              :sheets="sheets"
            />
            <div
              v-else-if="json"
              class="file-preview-text"
              data-testid="file-preview-json"
            >
              <FileJsonTree :value="json.value" />
            </div>
            <FileDocument
              v-else-if="kind === 'document'"
              :nodes="documentNodes"
            />
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
  /* The image's fit reads the body's size (`cqw`, `cqh`). */
  container-type: size;
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
  /* Until it loaded and its fit is known: never wider than the viewer. */
  max-width: 100%;
  height: auto;
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
