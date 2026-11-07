// The test helper of a window whose fields are refused with the same words (hub#888) passes a window whose every field
// carries the name the server refuses it by — an ion-input, an ion-textarea and an ion-select — and catches each way a
// window can get it wrong: fields without their name (FormModal falls back to the words, and the same words tell no
// field apart: correcting one leaves them all marked), a field named after another key (correcting it takes the
// other's mark away), and a test that does not refuse the fields with the same words at all (it would prove nothing).
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import { flush, mountBase } from './mount-base';
import { expectTheCorrectedFieldAloneLosesItsMark, refusedWithTheSameWords, SAME_WORDS } from './same-words-refusal';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const KEYS = ['title', 'notes', 'kind'] as const;

/** A window with a field per key — `title` an ion-input, `notes` an ion-textarea, `kind` an ion-select — whose «Save»
 *  is refused with `refusal`; each field carries the name `names` gives it (none when it gives none). */
async function windowNaming(names: Partial<Record<(typeof KEYS)[number], string>>, refusal = refusedWithTheSameWords(KEYS).error) {
  const error = ref<FormModalError | null>(null);
  const Window = defineComponent({
    setup() {
      const field = (key: (typeof KEYS)[number], errorText: string | undefined) => ({
        'data-testid': `thing-${key}`,
        name: names[key],
        errorText,
        class: errorText ? 'ion-invalid ion-touched' : undefined,
      });
      return () =>
        h(
          FormModal,
          { open: true, title: 'New thing', testid: 'thing', error: error.value, onSubmit: () => (error.value = refusal) },
          {
            default: ({ fieldErrors }: { fieldErrors: Record<string, string> }) => [
              h(IonInput, { ...field('title', fieldErrors.title), label: 'Title' }),
              h(IonTextarea, { ...field('notes', fieldErrors.notes), label: 'Notes' }),
              h(IonSelect, { ...field('kind', fieldErrors.kind), label: 'Kind', value: 'a' }, () => [h(IonSelectOption, { value: 'a' }, () => 'A')]),
            ],
          },
        );
    },
  });
  const m = await mountBase(Window);
  const settle = async () => {
    await nextTick();
    await flush();
    await flush();
  };
  await settle();
  return {
    field: (key: string) => document.querySelector(`[data-testid="thing-${key}"]`),
    send: async () => {
      m.wrapper.findComponent(FormModal).vm.$emit('submit');
      await settle();
    },
    settle,
  };
}

const NAMED = { title: 'title', notes: 'notes', kind: 'kind' };

describe('expectTheCorrectedFieldAloneLosesItsMark (hub#888)', () => {
  it.each(KEYS)('passes a window whose fields carry their names: %s, corrected, alone loses the words', async (key) => {
    const w = await windowNaming(NAMED);
    await expect(expectTheCorrectedFieldAloneLosesItsMark(w, KEYS, key)).resolves.toBeUndefined();
  });

  it.each(KEYS)('fails a window whose %s carries no name: correcting it leaves every field marked', async (key) => {
    const w = await windowNaming({ ...NAMED, [key]: undefined });
    await expect(expectTheCorrectedFieldAloneLosesItsMark(w, KEYS, key)).rejects.toThrow(new RegExp(`"${key}"`));
  });

  it('fails a window whose field is named after another key: correcting it takes the other’s mark away', async () => {
    const w = await windowNaming({ ...NAMED, title: 'notes' });
    await expect(expectTheCorrectedFieldAloneLosesItsMark(w, KEYS, 'title')).rejects.toThrow(/"title"/);
  });

  it('fails a test whose refusal does not say the same words under every field (it would prove nothing)', async () => {
    const w = await windowNaming(NAMED, { message: 'Check the highlighted details.', fields: { title: SAME_WORDS, notes: 'Another thing.', kind: SAME_WORDS } });
    await expect(expectTheCorrectedFieldAloneLosesItsMark(w, KEYS, 'title')).rejects.toThrow(/the same words/);
  });

  it('fails a test whose refusal leaves a field out', async () => {
    const w = await windowNaming(NAMED, refusedWithTheSameWords(['title', 'notes']).error);
    await expect(expectTheCorrectedFieldAloneLosesItsMark(w, KEYS, 'title')).rejects.toThrow(/the same words/);
  });

  it('builds the refusal the server sends: every key with the same words, in English or in the words it is given', () => {
    expect(refusedWithTheSameWords(['a', 'b'])).toEqual({
      error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { a: SAME_WORDS, b: SAME_WORDS } },
    });
    expect(refusedWithTheSameWords(['a'], 'Revisa este campo.').error.fields).toEqual({ a: 'Revisa este campo.' });
  });
});
