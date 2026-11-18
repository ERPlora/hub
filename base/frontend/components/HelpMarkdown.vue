<script setup lang="ts">
import { AssistantMarkdown } from '@erplora/ui/components';
import { useRouter } from 'vue-router';

defineProps<{ text: string }>();
const emit = defineEmits<{ go: [path: string] }>();
const router = useRouter();

const screenExists = (path: string): boolean => router.resolve(path).name !== 'not-found';
const nameOf = (): undefined => undefined;
</script>

<template>
  <AssistantMarkdown
    :text="text"
    :screen-exists="screenExists"
    :name-of="nameOf"
    @go="emit('go', $event)"
  />
</template>
