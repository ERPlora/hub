// A step of another app as the charge sheet sees it (lib/checkout/steps.ts): it paints what it is given, says what it
// adds whenever `adds` changes, and records its part of a charged sale with `record`.
import { defineComponent, h, watch } from 'vue';

import type { Added } from '../../../lib/checkout/steps';
import type { SaleOut } from '../../../operations';

export type Recorder = (sale: SaleOut, key: string) => Promise<void>;

/** Paints «<total>/<discount>/<method id>/<locked>» under `testid`. */
export function fakeStep(testid: string, adds: () => Added, record: Recorder) {
  return defineComponent({
    props: {
      total: { type: Number, required: true },
      discount: { type: Number, required: true },
      method: { type: Object, required: true },
      locked: { type: Boolean, required: true },
    },
    emits: ['update:added'],
    setup(props, { emit, expose }) {
      watch(adds, (now) => emit('update:added', now), { immediate: true });
      expose({ afterCharge: record });
      return () => h('p', { 'data-testid': testid }, `${props.total}/${props.discount}/${(props.method as { id: string }).id}/${props.locked}`);
    },
  });
}
