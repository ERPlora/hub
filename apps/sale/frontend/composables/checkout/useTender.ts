// The tender of the charge sheet (SALE-F01, F02, F03): which method charges, what the keypad holds, the
// change and, after «Split the payment», the legs taken (each can be edited back into the keypad or
// removed). The total and the cash limit are the server's (`sale.checkout.preview`); this only keeps
// what the person chose and typed. The arithmetic is lib/checkout/tender.ts.
import { computed, type MaybeRefOrGetter, shallowRef, toValue } from 'vue';

import { cashOverLimit, defaultMethod, isCash } from '../../lib/checkout/methods';
import {
  centsToTyped,
  changeDue,
  type Leg,
  needsTendered,
  paymentsIn,
  planLeg,
  pushKey,
  remainingCents,
  type TenderMethod,
  typedCents,
} from '../../lib/checkout/tender';
import type { PaymentIn } from '../../operations';

export interface UseTenderOptions<M extends TenderMethod> {
  /** The server's total of this charge; `undefined` while it loads. */
  total: MaybeRefOrGetter<number | undefined>;
  /** The methods offered, cash first. */
  methods: MaybeRefOrGetter<readonly M[]>;
  /** From this total on, no cash (the preview's `cash_limit`). */
  cashLimit: MaybeRefOrGetter<number | null | undefined>;
}

export function useTender<M extends TenderMethod>(options: UseTenderOptions<M>) {
  const pickedId = shallowRef<string | null>(null);
  const text = shallowRef('');
  /** After a leg comes back to be edited, the next key replaces its amount instead of extending it. */
  const primed = shallowRef(false);
  const splitting = shallowRef(false);
  const legs = shallowRef<Leg[]>([]);
  let legSeq = 0;

  const total = computed(() => toValue(options.total) ?? 0);
  const cashOff = computed(() => cashOverLimit(toValue(options.cashLimit), toValue(options.total)));
  const method = computed<M | undefined>(() => {
    const methods = toValue(options.methods);
    return methods.find((m) => m.id === pickedId.value) ?? defaultMethod(methods, cashOff.value);
  });
  const typed = computed(() => typedCents(text.value));
  const remaining = computed(() => remainingCents(total.value, legs.value));
  /** The leg «Add this payment» would take now. */
  const pending = computed(() => (splitting.value ? planLeg(method.value, typed.value, remaining.value) : undefined));
  const change = computed(() => {
    if (!splitting.value) return needsTendered(method.value) ? Math.max(0, typed.value - total.value) : 0;
    const next = pending.value && method.value ? [{ id: 'pending', method: method.value, ...pending.value }] : [];
    return changeDue([...legs.value, ...next]);
  });

  /** Chooses a method; cash over the legal limit is refused (`false`): the sheet says why. */
  function pick(next: M): boolean {
    if (cashOff.value && isCash(next)) return false;
    pickedId.value = next.id;
    if (!needsTendered(next) && !splitting.value) text.value = '';
    return true;
  }

  function press(key: string): void {
    text.value = pushKey(primed.value ? '' : text.value, key);
    primed.value = false;
  }

  function startSplit(): void {
    if (total.value > 0) splitting.value = true;
  }

  function addLeg(): void {
    const plan = pending.value;
    if (!plan || !method.value) return;
    legs.value = [...legs.value, { id: `leg-${++legSeq}`, method: method.value, ...plan }];
    text.value = '';
    primed.value = false;
  }

  function removeLeg(id: string): void {
    legs.value = legs.value.filter((leg) => leg.id !== id);
  }

  /** Back to the keypad with its method and what was handed over, to be taken again. */
  function editLeg(id: string): void {
    const leg = legs.value.find((l) => l.id === id);
    if (!leg) return;
    removeLeg(id);
    pickedId.value = leg.method.id;
    text.value = centsToTyped(leg.tendered);
    primed.value = true;
  }

  function payments(): PaymentIn[] {
    return paymentsIn({ total: total.value, method: method.value, typed: typed.value, splitting: splitting.value, legs: legs.value });
  }

  return { method, typed, cashOff, splitting, legs, remaining, change, pick, press, startSplit, addLeg, editLeg, removeLeg, payments };
}

export type Tender<M extends TenderMethod = TenderMethod> = ReturnType<typeof useTender<M>>;
