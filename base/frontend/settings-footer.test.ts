// Every settings form of the Hub ends the same way (hub#897): the refusal's red notice, «Settings saved» and «Save»
// are `SettingsFormFooter` of `@erplora/ui/components`, painted from what `useSettingsForm` gives, one line per page.
// A page that writes that end by hand has to be fixed page by page each time it changes: hub#854 changed the red
// notice by hand in six pages and hub#873 in the seventh. This guard reads every `.vue` under `apps/*/frontend`
// (tests and their helpers left out) whose script builds its form with `useSettingsForm`, and there may be none that
// does not end it with `<SettingsFormFooter`.
import { describe, expect, it } from 'vitest';

import { settingsForms } from './__tests__/settings-form';

describe('settings forms end with SettingsFormFooter (hub#897)', () => {
  const forms = settingsForms();

  it('finds the settings forms it guards', () => {
    expect(forms.length).toBeGreaterThan(0);
  });

  it('every form built on useSettingsForm paints its end with SettingsFormFooter, never by hand', () => {
    const byHand = forms.filter(({ source }) => !/<SettingsFormFooter\b/.test(source)).map(({ file }) => file);
    expect(byHand, 'end the form with <SettingsFormFooter :settings="…" testid="<app>-settings" … /> of @erplora/ui/components').toEqual([]);
  });
});
