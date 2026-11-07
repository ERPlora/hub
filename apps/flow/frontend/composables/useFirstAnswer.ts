// `useFirstAnswer(read, then)`: calls `then` once, the first time a live read has its answer — its data or its
// failure. The sections above the gallery of «Automations» (the questions, the drafts, the list) tell the page so:
// it says «Loading…» until then (hub#950) and opens a linked card of the gallery only once they are painted
// (FLOW-F05).
import { type Ref, watch } from 'vue';

export interface LiveRead {
  data: Readonly<Ref<unknown>>;
  error: Readonly<Ref<unknown>>;
}

export function useFirstAnswer(read: LiveRead, then: () => void): void {
  let told = false;
  watch(
    () => read.data.value ?? read.error.value,
    (answer) => {
      if (answer && !told) {
        told = true;
        then();
      }
    },
    { immediate: true },
  );
}
