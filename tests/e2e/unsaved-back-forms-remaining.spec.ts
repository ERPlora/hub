// flow: BASE-F05 and BASE-F73 (hub#1046). The other remaining windows are covered by their component tests.
import { test } from '@playwright/test';

import { expectBackAsksOnDirtyForm, type UnsavedFormCase } from './unsaved-back-helpers';

const NEW_FOLDER: UnsavedFormCase = {
  app: 'files',
  flow: 'BASE-F73',
  route: '/files',
  add: 'files-new-folder',
  form: 'files-new-folder-dialog',
  field: 'files-new-folder-name',
};

test('BASE-F73 files: Android Back asks before discarding a dirty form and closes a clean one', async ({ page }) => {
  await expectBackAsksOnDirtyForm(page, NEW_FOLDER, 'HUB-1046');
});
