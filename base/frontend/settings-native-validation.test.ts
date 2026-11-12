// A settings form of the Hub never lets the browser judge it (hub#1237): its fields carry their range (`min`, `max`)
// for the number keyboard and the arrows, and a `<form>` without `novalidate` let the browser check it before sending:
// Enter in a field with a number out of range sent nothing and showed only the browser's own bubble, and «Save» in
// Time clock showed that bubble over the page's reason. The page and the server judge the form, and the reason goes
// under its field (APPOINTMENT-F19, ATTENDANCE-F04, KITCHEN-F26, ONLINE_BOOKING-F07, RESERVATION-F03, SERVICE-F11,
// STAFF-F22, TABLE-F08 «Si falla»), as Inventory's settings already did. This guard reads every `.vue` under
// `apps/*/frontend` whose script builds its form with `useSettingsForm` (tests and their helpers left out), and every
// `<form>` in them carries `novalidate`.
import { describe, expect, it } from 'vitest';

import { openingTags, settingsForms } from './__tests__/settings-form';

const formTags = (source: string): string[] => openingTags(source, ['form']);
/** Whether the tag carries the bare `novalidate` attribute. */
const noValidate = (tag: string): boolean => /\snovalidate(?=[\s/>])/i.test(tag);

describe('settings forms leave the judging to the page, never to the browser (hub#1237)', () => {
  const forms = settingsForms().filter(({ source }) => formTags(source).length > 0);

  it('finds the settings forms it guards', () => {
    expect(forms.length).toBeGreaterThan(0);
  });

  it('reads each form tag whole, and only form tags (the guard catches what it guards)', () => {
    expect(formTags('<form\n  v-else\n  class="a"\n  @submit.prevent="settingsForm.save()"\n>').map(noValidate)).toEqual([false]);
    expect(formTags('<form class="a" novalidate @submit.prevent="settings.save()">').map(noValidate)).toEqual([true]);
    expect(formTags('<form\n  novalidate\n>').map(noValidate)).toEqual([true]);
    // A `>` inside an attribute is the attribute's, not the end of the tag.
    expect(formTags('<form :class="{ wide: width > 600 }" novalidate>').map(noValidate)).toEqual([true]);
    // Another tag's `novalidate` and a longer name are not this form's.
    expect(formTags('<form class="a">\n<other-form novalidate />').map(noValidate)).toEqual([false]);
    expect(formTags('<formula novalidate />')).toEqual([]);
    expect(formTags('<form data-novalidate="x">').map(noValidate)).toEqual([false]);
  });

  it('every form built on useSettingsForm carries novalidate', () => {
    const judgedByTheBrowser = forms.filter(({ source }) => formTags(source).some((tag) => !noValidate(tag))).map(({ file }) => file);
    expect(judgedByTheBrowser, 'add `novalidate` to the <form>: the page and the server judge it, under each field').toEqual([]);
  });
});
