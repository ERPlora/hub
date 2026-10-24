<script setup lang="ts">
// An answer of the assistant with its format (BASE-G113): the tree of `lib/assistant-markdown.ts` painted with Vue's
// own elements — never `v-html`, so nothing the model writes is a tag. A link only to a screen this hub serves
// (`screenExists`), named as the menu names it when the answer gave it no label (`nameOf`, BASE-G114); clicking it
// emits `go` (the panel navigates). Any other path is text. A table scrolls sideways inside its own box.
import { computed, type FunctionalComponent, h, type VNodeChild } from 'vue';

import { type Inline, parseMarkdown } from '../../lib/assistant-markdown';

const props = defineProps<{
  text: string;
  screenExists: (path: string) => boolean;
  nameOf: (path: string) => string | undefined;
}>();
const emit = defineEmits<{ go: [path: string] }>();

const blocks = computed(() => parseMarkdown(props.text));

function paint(inline: Inline): VNodeChild {
  switch (inline.kind) {
    case 'text':
      return inline.text;
    case 'strong':
      return h('strong', inline.children.map(paint));
    case 'em':
      return h('em', inline.children.map(paint));
    case 'code':
      return h('code', inline.text);
    case 'link': {
      const label = inline.label ? inline.label.map(paint) : (props.nameOf(inline.path) ?? inline.path);
      if (!props.screenExists(inline.path)) return h('span', label);
      return h(
        'a',
        {
          class: 'assistant-link',
          href: inline.path,
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            emit('go', inline.path);
          },
        },
        label,
      );
    }
  }
}

const Inlines: FunctionalComponent<{ inlines: Inline[] }> = (inner) => inner.inlines.map(paint);
</script>

<template>
  <div class="assistant-md">
    <template
      v-for="(block, index) in blocks"
      :key="index"
    >
      <p v-if="block.kind === 'paragraph'">
        <Inlines :inlines="block.inlines" />
      </p>
      <component
        :is="`h${Math.min(block.level + 2, 6)}`"
        v-else-if="block.kind === 'heading'"
        class="assistant-md-heading"
      >
        <Inlines :inlines="block.inlines" />
      </component>
      <component
        :is="block.ordered ? 'ol' : 'ul'"
        v-else-if="block.kind === 'list'"
      >
        <li
          v-for="(item, itemIndex) in block.items"
          :key="itemIndex"
        >
          <Inlines :inlines="item" />
        </li>
      </component>
      <div
        v-else
        class="assistant-table"
      >
        <table>
          <thead>
            <tr>
              <th
                v-for="(cell, cellIndex) in block.head"
                :key="cellIndex"
              >
                <Inlines :inlines="cell" />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, rowIndex) in block.rows"
              :key="rowIndex"
            >
              <td
                v-for="(cell, cellIndex) in row"
                :key="cellIndex"
              >
                <Inlines :inlines="cell" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.assistant-md {
  overflow-wrap: anywhere;
  line-height: 1.45;
}
.assistant-md p {
  margin: 0 0 8px;
  white-space: pre-line;
}
.assistant-md p:last-child,
.assistant-md ul:last-child,
.assistant-md ol:last-child {
  margin-bottom: 0;
}
.assistant-md ul,
.assistant-md ol {
  margin: 0 0 8px;
  padding-inline-start: 20px;
}
.assistant-md-heading {
  margin: 4px 0 6px;
  font-size: 1em;
  font-weight: 600;
}
.assistant-md code {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--ion-color-light, #f4f5f8);
  font-size: 0.92em;
}
.assistant-link {
  color: var(--ion-color-primary);
  text-decoration: underline;
  cursor: pointer;
}
/* A table scrolls inside its own box: at 390 px the panel never moves sideways (BASE-G113). */
.assistant-table {
  max-width: 100%;
  margin: 0 0 8px;
  overflow-x: auto;
}
.assistant-table table {
  border-collapse: collapse;
  font-size: 0.92em;
}
.assistant-table th,
.assistant-table td {
  padding: 4px 8px;
  border: 1px solid var(--ion-color-step-150, #e3e3e3);
  text-align: start;
  white-space: nowrap;
}
.assistant-table th {
  font-weight: 600;
}
</style>
