import { afterEach, describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import type { ReleaseNote } from '../operations/system';
import SystemReleaseNotes from './SystemReleaseNotes.vue';

const PATH = '/api/system/release-notes';

const ALLERGENS: ReleaseNote = {
  id: '2026-11-19-allergens',
  date: '2026-11-19',
  kind: 'new',
  title: 'Allergens on every product',
  body: 'Mark which allergens each product contains.',
};
const TABLES: ReleaseNote = { id: '2026-11-12-tables', date: '2026-11-12', kind: 'improved', title: 'Faster tables', body: 'The floor opens faster.' };
const PRINTER: ReleaseNote = { id: '2026-11-03-printer', date: '2026-11-03', kind: 'fixed', title: 'The printer reconnects', body: 'It comes back alone.' };

const page = (items: ReleaseNote[]) => ({ items, total: items.length });

/** Mounts the list with the API holding its answer until `answer` is called with one. */
async function held(options: Parameters<typeof mountBase>[1] = {}) {
  const answers: ((response: Response) => void)[] = [];
  const m = await mountBase(SystemReleaseNotes, {
    ...options,
    onApi: () => new Promise<Response>((resolve) => answers.push(resolve)),
  });
  async function answer(response: Response, index = answers.length - 1) {
    answers[index]!(response);
    await flush();
  }
  return { ...m, answer, asked: () => m.sent().filter((call) => call.path === PATH) };
}

async function listing(items: ReleaseNote[], options: Parameters<typeof mountBase>[1] = {}) {
  const m = await held(options);
  await m.answer(Response.json(page(items)));
  return m;
}

const rows = (m: Awaited<ReturnType<typeof held>>) => m.wrapper.findAll('[data-testid="system-release-note"]');
const field = (row: ReturnType<typeof rows>[number], name: string) => row.find(`[data-testid="system-release-note-${name}"]`).text();

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SystemReleaseNotes', () => {
  it('asks once for the most recent notes, the page the hub gives by default', async () => {
    const m = await held();
    expect(m.asked()).toEqual([{ method: 'GET', path: PATH, query: {}, body: undefined }]);
  });

  it('lists each note as the hub sends them: its day, its kind, its title and its text', async () => {
    const m = await listing([ALLERGENS, TABLES, PRINTER]);
    expect(m.find('system-release-notes').find('h3').text()).toBe("What's new");
    expect(rows(m).map((row) => row.attributes('data-id'))).toEqual([ALLERGENS.id, TABLES.id, PRINTER.id]);
    const [first] = rows(m);
    expect(field(first!, 'day')).toBe('Nov 19, 2026');
    expect(first!.find('time').attributes('datetime')).toBe('2026-11-19');
    expect(field(first!, 'title')).toBe('Allergens on every product');
    expect(field(first!, 'body')).toBe('Mark which allergens each product contains.');
    expect(rows(m).map((row) => field(row, 'kind'))).toEqual(['New', 'Improved', 'Fixed']);
  });

  it('in Spanish, with the day in its format', async () => {
    const m = await listing([ALLERGENS, TABLES, PRINTER], { locale: 'es' });
    expect(m.find('system-release-notes').find('h3').text()).toBe('Novedades');
    expect(field(rows(m)[0]!, 'day')).toBe('19 nov 2026');
    expect(rows(m).map((row) => field(row, 'kind'))).toEqual(['Nuevo', 'Mejora', 'Arreglo']);
  });

  it('shows the text as it comes, never as markup', async () => {
    const m = await listing([{ ...ALLERGENS, title: '<b>Bold</b>', body: '**Not bold** <i>nor this</i>' }]);
    const [row] = rows(m);
    expect(field(row!, 'title')).toBe('<b>Bold</b>');
    expect(field(row!, 'body')).toBe('**Not bold** <i>nor this</i>');
    expect(row!.find('b').exists()).toBe(false);
    expect(row!.find('i').exists()).toBe(false);
  });

  it('says it is reading until the hub answers, never an empty card', async () => {
    const m = await held();
    const loading = m.find('system-release-notes-loading');
    expect(loading.attributes('role')).toBe('status');
    expect(loading.text()).toBe("Reading what's new…");
    expect(m.find('system-release-notes-empty').exists()).toBe(false);
    await m.answer(Response.json(page([ALLERGENS])));
    expect(m.find('system-release-notes-loading').exists()).toBe(false);
    expect(rows(m)).toHaveLength(1);
  });

  it('reading, in Spanish', async () => {
    const m = await held({ locale: 'es' });
    expect(m.find('system-release-notes-loading').text()).toBe('Consultando las novedades…');
  });

  it('with none, says there is nothing new yet', async () => {
    const m = await listing([]);
    expect(m.find('system-release-notes-empty').text()).toBe('Nothing new yet.');
    expect(rows(m)).toHaveLength(0);
    const es = await listing([], { locale: 'es' });
    expect(es.find('system-release-notes-empty').text()).toBe('Todavía no hay novedades.');
  });

  it('a failed read says so, and «Retry» asks again', async () => {
    const m = await held();
    await m.answer(Response.json({ error: { code: 'internal_error', message: 'x' } }, { status: 500 }));
    expect(m.find('system-release-notes-loading').exists()).toBe(false);
    expect(m.find('system-release-notes-error').text()).toContain("Could not load what's new");
    await m.find('system-release-notes-retry').trigger('click');
    await flush();
    expect(m.asked()).toHaveLength(2);
    expect(m.find('system-release-notes-error').exists()).toBe(false);
    await m.answer(Response.json(page([ALLERGENS])));
    expect(rows(m)).toHaveLength(1);
  });

  it('a failed read, in Spanish', async () => {
    const m = await held({ locale: 'es' });
    await m.answer(Response.json({ error: { code: 'internal_error', message: 'x' } }, { status: 500 }));
    expect(m.find('system-release-notes-error').text()).toContain('No se pudieron cargar las novedades');
    expect(m.find('system-release-notes-retry').text()).toBe('Reintentar');
  });

  it('asks again when the person changes language, since the hub answers in theirs', async () => {
    const m = await listing([ALLERGENS]);
    await m.setLocale('es');
    expect(m.asked()).toHaveLength(2);
    await m.answer(Response.json(page([{ ...ALLERGENS, title: 'Alérgenos en cada producto' }])));
    expect(field(rows(m)[0]!, 'title')).toBe('Alérgenos en cada producto');
  });
});
