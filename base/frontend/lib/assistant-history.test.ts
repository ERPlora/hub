// BASE-G120: the conversation lives only in this tab of the person's browser (sessionStorage), never on a server;
// another person on the same till starts empty (gh:hub#2538). Cases of the old hub's `assistant-history.test.ts`.
import { describe, expect, it } from 'vitest';

import { memoryStorage } from '../__tests__/mount-base';
import { clearThread, emptyThread, HISTORY_KEY, loadThread, saveThread, type Thread } from './assistant-history';

function thread(fields: Partial<Thread> = {}): Thread {
  return {
    ...emptyThread('u1'),
    conversation: [{ role: 'user', content: 'hola' }, { role: 'assistant', content: 'Hola, Ana' }],
    bubbles: [
      { id: 'b1', role: 'user', text: 'hola', files: [], notices: [], done: true },
      { id: 'b2', role: 'assistant', text: 'Hola, Ana', files: [], notices: [], done: true },
    ],
    ...fields,
  };
}

describe('the thread of a tab', () => {
  it('starts empty when nothing was kept', () => {
    expect(loadThread(memoryStorage(), 'u1')).toEqual(emptyThread('u1'));
  });

  it('is kept and read back after a reload, in the same tab', () => {
    const storage = memoryStorage();
    saveThread(storage, thread());
    expect(loadThread(storage, 'u1')).toEqual(thread());
  });

  it('is never another person’s: who comes in after a switch starts empty, and the old one is gone', () => {
    const storage = memoryStorage();
    saveThread(storage, thread());
    expect(loadThread(storage, 'u2')).toEqual(emptyThread('u2'));
    expect(storage.getItem(HISTORY_KEY)).toBeNull();
  });

  it('a broken thread starts empty, without throwing', () => {
    const storage = memoryStorage();
    storage.setItem(HISTORY_KEY, '{not json');
    expect(loadThread(storage, 'u1')).toEqual(emptyThread('u1'));
  });

  it('an answer cut by a reload is kept as cut, never dots forever', () => {
    const storage = memoryStorage();
    saveThread(storage, thread({ bubbles: [{ id: 'b1', role: 'assistant', text: 'Tienes', files: [], notices: [], done: false }] }));
    expect(loadThread(storage, 'u1').bubbles[0]).toMatchObject({ text: 'Tienes', done: true, error: 'assistant.cut' });
  });

  it('keeps the name of an attachment, not its data (it went with its question)', () => {
    const storage = memoryStorage();
    const withFile = thread({
      conversation: [
        {
          role: 'user',
          content: [
            { type: 'text', text: 'lee esto' },
            { type: 'input_file', filename: 'carta.pdf', mime_type: 'application/pdf', data: 'JVBERi0x' },
            { type: 'image_url', image_url: { url: 'data:image/png;base64,iVBOR' }, filename: 'foto.png' },
          ],
        },
      ],
    });
    saveThread(storage, withFile);
    expect(loadThread(storage, 'u1').conversation[0].content).toEqual([
      { type: 'text', text: 'lee esto' },
      { type: 'text', text: '[Attached: carta.pdf]' },
      { type: 'text', text: '[Attached: foto.png]' },
    ]);
    expect(storage.getItem(HISTORY_KEY)).not.toContain('JVBERi0x');
  });

  it('a storage that refuses (private mode, full) is ignored: the thread lives on in memory', () => {
    const refusing = { ...memoryStorage(), setItem: () => { throw new Error('QuotaExceededError'); } } as Storage;
    expect(() => saveThread(refusing, thread())).not.toThrow();
  });

  it('clearing it removes it', () => {
    const storage = memoryStorage();
    saveThread(storage, thread());
    clearThread(storage);
    expect(storage.getItem(HISTORY_KEY)).toBeNull();
  });
});
