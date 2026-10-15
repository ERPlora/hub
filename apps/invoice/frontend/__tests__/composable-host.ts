// The one host of a composable under test (its own file: one component per file): runs `use` in its
// setup and renders nothing. `mountComposable` of mount-invoice.ts mounts it in the invoice app's harness.
import { defineComponent, h } from 'vue';

export const ComposableHost = defineComponent({
  props: { use: { type: Function, required: true } },
  setup(props) {
    props.use();
    return () => h('div');
  },
});
