// The buttons of «Files» whose icon says them alone are that icon, named and titled by their label: «Upload file» and
// the «⋮» of the open folder and of each file. «New folder» keeps its words: a folder alone names the folders.
import { describe, expect, it } from 'vitest';

import { iconOnly, iconOnlyNamed } from '../__tests__/icon-only';
import { mountBase, OWNER } from '../__tests__/mount-base';
import type { FilesListing } from '../operations/files';
import FilesPage from './FilesPage.vue';

const ADMIN = { ...OWNER, permissions: [...OWNER.permissions, 'base.view_files', 'base.upload_files', 'base.delete_files'] };

const LISTING: FilesListing = {
  folder: 'Facturas',
  crumbs: [{ path: 'Facturas', name: 'Facturas' }],
  folders: [{ path: 'Facturas', name: 'Facturas', children: [] }],
  files: [
    {
      path: 'Facturas/marzo.pdf',
      name: 'marzo.pdf',
      size: 2048,
      modified: '2026-10-24T08:00:00Z',
      content_type: 'application/pdf',
      preview: 'pdf',
    },
  ],
  space: { used_bytes: 2048, limit_bytes: null },
  can: { upload: true, delete: true },
};

async function open(locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FilesPage, { path: '/files?folder=Facturas', routes: ['/files'], session: ADMIN, stubs: { FilePreview: true }, locale });
  await m.result(await m.live(), 'base.file.list', LISTING);
  return m;
}

describe('FilesPage: its action buttons', () => {
  it('«Upload file» is its cloud alone; «New folder» keeps its words', async () => {
    const m = await open();
    expect(iconOnly(m.wrapper.get('[data-testid="files-upload"]'))).toEqual(iconOnlyNamed('Upload file'));
    expect(m.wrapper.get('[data-testid="files-new-folder"]').text()).toBe('New folder');
  });

  it('the «⋮» of the open folder and of each file are titled with what they act on', async () => {
    const m = await open('es');
    expect(iconOnly(m.wrapper.get('[data-testid="files-folder-actions"]'))).toEqual(iconOnlyNamed('Acciones de «Facturas»'));
    expect(iconOnly(m.wrapper.get('[data-item="Facturas/marzo.pdf"] [data-testid="files-item-actions"]'))).toEqual(
      iconOnlyNamed('Acciones de «marzo.pdf»'),
    );
  });
});
