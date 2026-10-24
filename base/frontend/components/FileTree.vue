<script setup lang="ts">
// Files › the tree of folders (BASE-G82, BASE-G85; the old hub's ok-file-manager tree): the folders of the business,
// nested, the open one marked (`aria-current`); a tap opens one, and what is dragged from the list (`dragging`, its
// path) drops on a folder to move there — only where the person may move (`droppable`), never onto itself or inside
// itself. Content of the page, not a menu: its rows are buttons.
import { HubIcon } from '@erplora/ui/shell';
import { ref } from 'vue';

import type { FileFolder } from '../operations';

defineOptions({ name: 'FileTree' });

const props = defineProps<{ nodes: FileFolder[]; selected: string; droppable: boolean; dragging: string | null }>();
const emit = defineEmits<{ select: [path: string]; drop: [path: string] }>();

const target = ref<string | null>(null);

function accepts(path: string): boolean {
  const from = props.dragging;
  return props.droppable && !!from && path !== from && !path.startsWith(`${from}/`);
}

function over(event: DragEvent, path: string): void {
  if (!accepts(path)) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  target.value = path;
}

function dropped(event: DragEvent, path: string): void {
  target.value = null;
  if (!accepts(path)) return;
  event.preventDefault();
  emit('drop', path);
}
</script>

<template>
  <ul class="file-tree">
    <li
      v-for="node in nodes"
      :key="node.path"
    >
      <button
        type="button"
        class="file-tree-node"
        :class="{ 'file-tree-open': node.path === selected, 'file-tree-target': target === node.path }"
        :data-folder="node.path"
        :aria-current="node.path === selected ? 'true' : undefined"
        @click="emit('select', node.path)"
        @dragover="over($event, node.path)"
        @dragleave="target = target === node.path ? null : target"
        @drop="dropped($event, node.path)"
      >
        <HubIcon
          name="ion:folder-outline"
          decorative
        />
        <span class="file-tree-name">{{ node.name }}</span>
      </button>
      <FileTree
        v-if="node.children.length"
        class="file-tree-children"
        :nodes="node.children"
        :selected="selected"
        :droppable="droppable"
        :dragging="dragging"
        @select="emit('select', $event)"
        @drop="emit('drop', $event)"
      />
    </li>
  </ul>
</template>

<style scoped>
.file-tree {
  margin: 0;
  padding: 0;
  list-style: none;
}

.file-tree-children {
  padding-inline-start: 16px;
}

.file-tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.file-tree-node:hover,
.file-tree-node:focus-visible {
  background: var(--ion-color-light, #f4f5f8);
}

.file-tree-open {
  background: var(--ion-color-primary-tint, #e6f0ff);
  color: var(--ion-color-primary-shade, #0b5ed7);
  font-weight: 600;
}

.file-tree-target {
  border-color: var(--ion-color-primary, #3880ff);
  border-style: dashed;
}

.file-tree-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
