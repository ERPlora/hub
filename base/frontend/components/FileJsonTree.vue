<script setup lang="ts">
// Files › the preview of a JSON (hub#578, BASE-F74; the old hub's JSON viewer): a tree that folds and unfolds by parts,
// as the browsers' JSON viewers do. Each object or array is a native disclosure (`<details>`: keyboard and screen
// reader for free) that says how much it holds; its first levels open (`JSON_OPEN_DEPTH`), and a folded one draws
// nothing until it opens, so a big file costs only what is opened. An opened one draws its first `JSON_TREE_ENTRIES`
// entries and says how many more there are. A value reads as JSON writes it, always as text (never markup).
import { computed, ref } from 'vue';

import { JSON_OPEN_DEPTH, JSON_TREE_ENTRIES } from '../lib/files';
import { useBaseI18n } from '../lib/i18n';

defineOptions({ name: 'FileJsonTree' });

const props = withDefaults(defineProps<{ value: unknown; name?: string | null; depth?: number }>(), {
  name: null,
  depth: 0,
});

const { t } = useBaseI18n();

const isBranch = computed(() => props.value !== null && typeof props.value === 'object');
const isList = computed(() => Array.isArray(props.value));
const entries = computed(() => (isBranch.value ? Object.entries(props.value as object) : []));
const shown = computed(() => entries.value.slice(0, JSON_TREE_ENTRIES));
const more = computed(() => entries.value.length - shown.value.length);
const opened = ref(props.depth < JSON_OPEN_DEPTH);

const bracket = computed(() => (isList.value ? '[ ]' : '{ }'));
const holds = computed(() => {
  const count = entries.value.length;
  if (isList.value) return count === 1 ? t('base.files.preview.json.oneItem') : t('base.files.preview.json.items', { count });
  return count === 1 ? t('base.files.preview.json.oneField') : t('base.files.preview.json.fields', { count });
});
/** A value as JSON writes it: a text in quotes and escaped, a number, true, false or null. */
const written = computed(() => JSON.stringify(props.value) ?? String(props.value));
const valueKind = computed(() => (props.value === null ? 'null' : typeof props.value));

function toggled(event: Event): void {
  // Its own disclosure: a nested one's toggle must never fold this one.
  opened.value = (event.currentTarget as HTMLDetailsElement).open;
}
</script>

<template>
  <details
    v-if="isBranch"
    class="file-json-branch"
    data-testid="file-json-branch"
    :open="opened"
    @toggle="toggled"
  >
    <summary
      class="file-json-summary"
      data-testid="file-json-summary"
    >
      <span
        v-if="name !== null"
        class="file-json-key"
      >{{ name }}:</span>
      {{ bracket }}
      <span class="file-json-count">{{ holds }}</span>
    </summary>
    <div
      v-if="opened"
      class="file-json-entries"
    >
      <FileJsonTree
        v-for="[key, child] in shown"
        :key="key"
        :value="child"
        :name="key"
        :depth="depth + 1"
      />
      <p
        v-if="more > 0"
        class="file-json-more"
        data-testid="file-json-more"
      >
        {{ t('base.files.preview.json.more', { count: more }) }}
      </p>
    </div>
  </details>
  <div
    v-else
    :class="['file-json-leaf', `file-json-leaf--${valueKind}`]"
    data-testid="file-json-leaf"
  >
    <span
      v-if="name !== null"
      class="file-json-key"
    >{{ name }}:</span>
    {{ written }}
  </div>
</template>

<style scoped>
.file-json-branch,
.file-json-leaf {
  font-family: var(--ep-font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  font-size: 0.8125rem;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.file-json-summary {
  cursor: pointer;
}

.file-json-entries {
  padding-inline-start: 1.25rem;
  border-inline-start: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  margin-inline-start: 0.3rem;
}

.file-json-leaf {
  padding-inline-start: 1rem;
}

.file-json-key {
  color: var(--ion-color-primary-shade, #3171e0);
}

.file-json-count,
.file-json-more {
  color: var(--ion-color-medium-shade, #555);
}

.file-json-more {
  margin: 0;
  padding-inline-start: 1rem;
}

.file-json-leaf--string {
  color: var(--ion-color-success-shade, #2a8a4b);
}

.file-json-leaf--number,
.file-json-leaf--boolean,
.file-json-leaf--null {
  color: var(--ion-color-tertiary-shade, #4f4fd6);
}
</style>
