<script setup lang="ts">
// Files › the preview of a Word document (hub#578, BASE-F74): its text with its basic formatting (headings, bold,
// italics, underline, lists, tables, links and its own images), drawn element by element with Vue from the tree
// `readDocument` keeps (`lib/office.ts`), never HTML painted: no `v-html`/`innerHTML` (Trusted Types refuses them, and
// a document is a third party's). A link opens apart from the hub (the installed app hands it to the system browser).
import { openExternalLink } from '@erplora/ui/shell';
import { computed, h, type VNode } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { DocumentNode } from '../lib/office';
import '../file-viewers.css';

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

