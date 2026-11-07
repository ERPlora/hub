<script setup lang="ts">
// Files › the preview of a Word document (hub#578, BASE-F74): its text with its basic formatting (headings, bold,
// italics, underline, lists, tables, links and its own images), drawn element by element with Vue from the tree
// `readDocument` keeps (`lib/office.ts`), never HTML painted: no `v-html`/`innerHTML` (Trusted Types refuses them, and
// a document is a third party's). A link opens apart from the hub (the installed app hands it to the system browser).
import { openExternalLink } from '@erplora/ui/shell';
import { computed, h, type VNode } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { DocumentNode } from '../lib/office';

const props = defineProps<{ nodes: readonly DocumentNode[] }>();

const { t } = useBaseI18n();

function draw(node: DocumentNode): VNode | string {
  if (typeof node === 'string') return node;
  const children = node.children.map(draw);
  if (node.tag === 'a') {
    const href = node.attrs.href;
    return h('a', { href, target: '_blank', rel: 'noopener noreferrer', onClick: (event: Event) => openExternalLink(href, event) }, children);
  }
  return h(node.tag, { ...node.attrs }, children);
}

/** Whether `nodes` hold something to read: a text that is not blank, or an image. */
function filled(nodes: readonly DocumentNode[]): boolean {
  return nodes.some((node) => (typeof node === 'string' ? node.trim() !== '' : node.tag === 'img' || filled(node.children)));
}

const hasText = computed(() => filled(props.nodes));
const DocumentBody = () => props.nodes.map(draw);
</script>

<template>
  <p
    v-if="!hasText"
    class="file-document-empty"
    data-testid="file-preview-document-empty"
  >
    {{ t('base.files.preview.documentEmpty') }}
  </p>
  <article
    v-else
    class="file-document"
    data-testid="file-preview-document"
  >
    <DocumentBody />
  </article>
</template>

<style scoped>
.file-document {
  align-self: stretch;
  max-width: 48rem;
  margin-inline: auto;
  width: 100%;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.file-document-empty {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.file-document :deep(h1) {
  font-size: 1.5rem;
}

.file-document :deep(h2) {
  font-size: 1.25rem;
}

.file-document :deep(h3),
.file-document :deep(h4),
.file-document :deep(h5),
.file-document :deep(h6) {
  font-size: 1.0625rem;
}

.file-document :deep(table) {
  border-collapse: collapse;
  margin-block: 0.75rem;
  max-width: 100%;
  overflow-x: auto;
  display: block;
}

.file-document :deep(td),
.file-document :deep(th) {
  padding: 4px 8px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  vertical-align: top;
}

.file-document :deep(td p),
.file-document :deep(th p) {
  margin: 0;
}

.file-document :deep(img) {
  max-width: 100%;
  height: auto;
}
</style>
