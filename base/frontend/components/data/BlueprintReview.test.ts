// «Review what it brings» (BASE-G105): what a template or a file is (name, type, language and country by name, apps,
// when it was made), one box per app with what it brings — an app off or this hub does not have, and personal data in
// a template, say they stay out —, what this hub never loads, and «Import» with the apps ticked or «Choose another».
import { afterEach, describe, expect, it } from 'vitest';

import { summary } from '../../__tests__/data-fixtures';
import { flush, mountBase } from '../../__tests__/mount-base';
import BlueprintReview from './BlueprintReview.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

async function review(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountBase(BlueprintReview, { props: { summary: summary(), ...props }, locale });
}

const apps = (m: Awaited<ReturnType<typeof review>>) =>
  m.wrapper.findAll('[data-testid="review-app"]').map((row) => {
    const box = row.get('ion-checkbox').element as HTMLElement & { checked?: boolean; disabled?: boolean };
    return [row.attributes('data-id'), box.checked, box.disabled];
  });

describe('BlueprintReview', () => {
  it('says what it is: name, type, language and country by name, how many apps', async () => {
    const m = await review({}, 'es');
    const facts = m.wrapper.get('[data-testid="review-facts"]').text();
    for (const part of ['Restaurant', 'Plantilla', 'español', 'España', '4']) expect(facts).toContain(part);
    expect(facts).not.toContain('Creado');
  });

  it('says when a file was made', async () => {
    const m = await review({ summary: summary({ source: 'file', purpose: 'backup', created_at: '2026-10-20T10:00:00Z' }) });
    const facts = m.wrapper.get('[data-testid="review-facts"]').text();
    expect(facts).toContain('Backup');
    expect(facts).toContain('Created');
    expect(facts).toContain('2026');
  });

  it('ticks the apps on here; an app off or unknown here is out, saying why', async () => {
    const m = await review();
    expect(apps(m)).toEqual([
      ['inventory', true, false],
      ['customer', true, false],
      ['kitchen', false, true],
      ['mystery', false, true],
    ]);
    const text = m.wrapper.text();
    expect(text).toContain('Products · 12');
    expect(text).toContain('This app is off in your business: nothing of it will load.');
    expect(text).toContain('This business does not have this app: nothing of it will load.');
    expect(text).toContain('Personal data: it loads only from a backup.');
  });

  it('imports the apps ticked, in the file\'s order', async () => {
    const m = await review();
    m.wrapper.findAll('[data-testid="review-app"] ion-checkbox')[1].element.dispatchEvent(
      new CustomEvent('ionChange', { detail: { checked: false } }),
    );
    await flush();
    await m.wrapper.get('[data-testid="review-import"]').trigger('click');
    expect(m.wrapper.emitted('import')).toEqual([[['inventory']]]);
  });

  it('cannot import with no app ticked, and says so', async () => {
    const m = await review();
    for (const box of m.wrapper.findAll('[data-testid="review-app"] ion-checkbox').slice(0, 2)) {
      box.element.dispatchEvent(new CustomEvent('ionChange', { detail: { checked: false } }));
    }
    await flush();
    expect((m.wrapper.get('[data-testid="review-import"]').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    expect(m.wrapper.text()).toContain('Choose at least one app.');
  });

  it('ticks an app off that the load turns on, saying so, and imports it (round 2026-10-27)', async () => {
    const turnsOn = summary({
      apps: [
        { id: 'table', label: 'Tables', status: 'turns_on', datasets: [{ key: 'table.zone', label: 'Zones', rows: 2, personal: false, travels: true }] },
        { id: 'kitchen', label: 'Kitchen', status: 'inactive', datasets: [] },
      ],
    });
    const m = await review({ summary: turnsOn });
    expect(apps(m)).toEqual([
      ['table', true, false],
      ['kitchen', false, true],
    ]);
    expect(m.wrapper.get('[data-id="table"]').text()).toContain('It is off in your business: loading it turns it on.');
    await m.wrapper.get('[data-testid="review-import"]').trigger('click');
    expect(m.wrapper.emitted('import')).toEqual([[['table']]]);
    const es = await review({ summary: turnsOn }, 'es');
    expect(es.wrapper.get('[data-id="table"]').text()).toContain('Está desactivada en tu negocio: se activará al cargarla.');
  });

  it('says when nothing of the file can load here', async () => {
    const m = await review({ summary: summary({ apps: [{ id: 'kitchen', label: 'Kitchen', status: 'inactive', datasets: [] }] }) });
    expect(m.wrapper.text()).toContain('Nothing of this file can load in your business: none of its apps can be turned on here.');
    expect((m.wrapper.get('[data-testid="review-import"]').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });

  it('lists what this hub never loads', async () => {
    const m = await review({ summary: summary({ dropped: ['People and their PINs'] }) });
    expect(m.wrapper.get('[data-testid="review-dropped"]').text()).toContain('People and their PINs');
  });

  it('works while importing, says why it failed, and goes back to choose another', async () => {
    const m = await review({ pending: true });
    const button = m.wrapper.get('[data-testid="review-import"]');
    expect(button.text()).toBe('Importing…');
    expect((button.element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    await m.wrapper.setProps({ pending: false, error: 'The app refused it.' });
    expect(m.wrapper.get('[data-testid="review-error"]').text()).toContain('The import failed: The app refused it.');
    await m.wrapper.get('[data-testid="review-back"]').trigger('click');
    expect(m.wrapper.emitted('back')).toHaveLength(1);
  });
});
