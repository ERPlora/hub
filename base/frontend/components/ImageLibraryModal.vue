<script setup lang="ts">
// «Image library» (INVENTORY-F30, SERVICE-F34, COMBO-F14): the window a product's, a service's or a set menu's
// «Photo» opens. The search box comes written with the item's name (`query`) and searches ERPlora's shared library
// (`base.catalog_image.search`) by title and synonyms, in Spanish or English, never by file name; under two letters
// it lists the whole library (or sector) by title. The sector tabs narrow it («All» first, then `folders` and the
// rest in the library's order); 60 at a time with «Load more». Each image shows with its title under it, in the
// business's language. Loading, empty and error («Retry») states; an answer that arrives after a newer search is
// dropped. A tap on an image emits `pick` and closes; «Upload photo» emits `upload` (the field opens the device's
// picker) and closes too. Hooks (`testid`): the root, `-search`, `-folders`, `-folder-<key>`, `-loading`, `-empty`,
// `-error`, `-retry`, `-image-<folder>-<name>`, `-count`, `-more`, `-upload`, `-close`.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonFooter,
  IonHeader,
  IonLabel,
  IonModal,
  IonSearchbar,
  IonSegment,
  IonSegmentButton,
  IonSkeletonText,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { CatalogImage } from '../operations';

/** The library's sectors, in its order (`blueprints/img/<folder>`). */
const FOLDERS = ['hospitality', 'beauty_hair', 'beauty_body', 'retail', 'fitness', 'wellness_spa'] as const;
const ALL = 'all';
const PAGE = 60;
/** Fewer letters than this search the whole library (by title). */
const MIN_QUERY = 2;

const props = withDefaults(
  defineProps<{
    /** What the box comes written with: the item's name. */
    query?: string;
    /** Sectors that go first after «All» (a service's: Hair and Beauty). */
    folders?: readonly string[];
    testid?: string;
  }>(),
  { query: '', folders: () => [], testid: 'image-library' },
);
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ pick: [image: CatalogImage]; upload: [] }>();

const { t } = useBaseI18n();
const client = useLiveClient();

const text = ref('');
const folder = ref<string>(ALL);
const rows = shallowRef<CatalogImage[]>([]);
const total = ref(0);
const status = ref<'loading' | 'ready' | 'error'>('loading');
const more = ref(false);
/** Each search's number: an answer to an older one is dropped. */
let seq = 0;

const tabs = computed(() => {
  const first = props.folders.filter((key) => (FOLDERS as readonly string[]).includes(key));
  return [ALL, ...first, ...FOLDERS.filter((key) => !first.includes(key))];
});

function input(offset: number) {
  const query = text.value.trim();
  return {
    query: query.length >= MIN_QUERY ? query : '',
    ...(folder.value !== ALL ? { folder: folder.value } : {}),
    limit: PAGE,
    offset,
  };
}

async function search(): Promise<void> {
  const mine = ++seq;
  status.value = 'loading';
  more.value = false;
  try {
    const page = await client.api.call('base.catalog_image.search', input(0));
    if (mine !== seq) return;
    rows.value = page.rows;
    total.value = page.total;
    status.value = 'ready';
  } catch {
    if (mine === seq) status.value = 'error';
  }
}

async function loadMore(): Promise<void> {
  if (more.value) return;
  const mine = seq;
  more.value = true;
  try {
    const page = await client.api.call('base.catalog_image.search', input(rows.value.length));
    if (mine !== seq) return;
    rows.value = [...rows.value, ...page.rows];
    total.value = page.total;
  } catch {
    if (mine === seq) status.value = 'error';
  } finally {
    if (mine === seq) more.value = false;
  }
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    text.value = props.query;
    folder.value = ALL;
    void search();
  },
  { immediate: true },
);

function onInput(value: unknown): void {
  text.value = value === null || value === undefined ? '' : String(value);
  void search();
}

function onFolder(value: unknown): void {
  const next = String(value ?? ALL);
  if (next === folder.value) return;
  folder.value = next;
  void search();
}

function pick(image: CatalogImage): void {
  emit('pick', image);
  open.value = false;
}

function upload(): void {
  emit('upload');
  open.value = false;
}

const tid = (part: string) => `${props.testid}-${part}`;
</script>

<template>
  <ion-modal
    :is-open="open"
    class="image-library"
    :data-testid="testid"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ t('base.imageLibrary.title') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            :data-testid="tid('close')"
            @click="open = false"
          >
            {{ t('base.imageLibrary.close') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
      <ion-toolbar>
        <ion-searchbar
          :data-testid="tid('search')"
          :value="text"
          :placeholder="t('base.imageLibrary.search')"
          :debounce="300"
          @ion-input="onInput($event.detail.value)"
        />
      </ion-toolbar>
      <ion-toolbar>
        <ion-segment
          :data-testid="tid('folders')"
          :value="folder"
          :scrollable="true"
          :aria-label="t('base.imageLibrary.folders.label')"
          @ion-change="onFolder($event.detail.value)"
        >
          <ion-segment-button
            v-for="key in tabs"
            :key="key"
            :value="key"
            :data-testid="tid(`folder-${key}`)"
          >
            <ion-label>{{ t(`base.imageLibrary.folders.${key}`) }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <InlineFeedback
        v-if="status === 'error'"
        tone="danger"
        :data-testid="tid('error')"
      >
        {{ t('base.imageLibrary.error') }}
        <template #actions>
          <ion-button
            :data-testid="tid('retry')"
            fill="outline"
            size="small"
            @click="search()"
          >
            {{ t('base.imageLibrary.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <div
        v-else-if="status === 'loading'"
        class="image-library__grid"
        role="status"
        :aria-label="t('base.imageLibrary.loading')"
        :data-testid="tid('loading')"
      >
        <div
          v-for="n in 12"
          :key="n"
          class="image-library__tile"
          aria-hidden="true"
        >
          <ion-skeleton-text
            :animated="true"
            class="image-library__skeleton"
          />
          <ion-skeleton-text
            :animated="true"
            class="image-library__skeleton-title"
          />
        </div>
      </div>
      <EmptyState
        v-else-if="!rows.length"
        :data-testid="tid('empty')"
        icon="image-outline"
        :heading="t('base.imageLibrary.empty')"
      />
      <template v-else>
        <div class="image-library__grid">
          <button
            v-for="image in rows"
            :key="image.reference"
            type="button"
            class="image-library__tile image-library__choice"
            :data-testid="tid(`image-${image.folder}-${image.name}`)"
            @click="pick(image)"
          >
            <img
              class="image-library__image"
              :src="image.url"
              :alt="image.title"
              loading="lazy"
              decoding="async"
            >
            <span class="image-library__title">{{ image.title }}</span>
          </button>
        </div>
        <div
          v-if="rows.length < total"
          class="image-library__more"
        >
          <span :data-testid="tid('count')">{{ t('base.imageLibrary.showing', { shown: rows.length, total }) }}</span>
          <ion-button
            :data-testid="tid('more')"
            fill="clear"
            :disabled="more"
            @click="loadMore()"
          >
            {{ t('base.imageLibrary.loadMore') }}
          </ion-button>
        </div>
      </template>
    </ion-content>
    <ion-footer>
      <ion-toolbar>
        <ion-buttons slot="end">
          <ion-button
            :data-testid="tid('upload')"
            fill="outline"
            @click="upload()"
          >
            {{ t('base.imageLibrary.upload') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-footer>
  </ion-modal>
</template>

<style scoped>
.image-library__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr));
  gap: 12px;
}
.image-library__tile {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.image-library__choice {
  margin: 0;
  padding: 6px;
  font: inherit;
  text-align: center;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
.image-library__choice:hover,
.image-library__choice:focus-visible {
  border-color: var(--ion-color-primary, #0091ce);
}
.image-library__image,
.image-library__skeleton {
  width: 100%;
  aspect-ratio: 1;
  margin: 0;
  object-fit: cover;
  background: #fff;
  border-radius: 8px;
}
.image-library__skeleton-title {
  width: 70%;
  height: 0.8rem;
  margin: 0 auto;
}
.image-library__title {
  overflow: hidden;
  font-size: 0.8rem;
  line-height: 1.2;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.image-library__more {
  display: grid;
  justify-items: center;
  gap: 4px;
  margin-top: 12px;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
