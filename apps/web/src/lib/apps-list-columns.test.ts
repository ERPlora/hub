// Regression test for ERPlora/hub#2245 — on a phone, the Apps list view was wider than the screen:
// app, version and a clipped category showed, while status and the row's action sat off to the
// right. The list view on a narrow screen keeps what a person scans the list for — which app, is it
// there — and the row's action (pinned by the table itself); the card view keeps every field.
import { describe, expect, it } from 'vitest';
import { columnsForScreen } from './apps-list-columns';

const catalog = [
  { key: 'name' },
  { key: 'version' },
  { key: 'cat' },
  { key: 'desc' },
  { key: 'price' },
  { key: 'stateLabel' },
];
const shown = (cols: { key: string; hidden?: boolean }[]) => cols.filter((c) => !c.hidden).map((c) => c.key);

describe('columnsForScreen (hub#2245)', () => {
  it('the list view on a narrow screen shows only the app and its status', () => {
    expect(shown(columnsForScreen(catalog, { compact: true, view: 'table' }))).toEqual(['name', 'stateLabel']);
  });

  // rv-2250: a column dropped from `columns` takes its filter and its sort with it (Category = Sales
  // picked on the cards, then «List view», and every app came back). The narrow list HIDES them.
  it('the narrow list hides the other columns instead of dropping them', () => {
    const narrow = columnsForScreen(catalog, { compact: true, view: 'table' });
    expect(narrow.map((c) => c.key)).toEqual(catalog.map((c) => c.key));
    expect(narrow.find((c) => c.key === 'cat')).toMatchObject({ key: 'cat', hidden: true });
  });

  it('the card view on a narrow screen keeps every field', () => {
    expect(columnsForScreen(catalog, { compact: true, view: 'cards' })).toBe(catalog);
  });

  it('a wide screen keeps every column in the list view', () => {
    expect(columnsForScreen(catalog, { compact: false, view: 'table' })).toBe(catalog);
  });
});
