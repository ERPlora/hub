import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const profile = readFileSync(new URL('./ProfilePage.vue', import.meta.url), 'utf8');

describe('profile language selector', () => {
  it('remounts Ionic select when the locale changes so its native aria-label is translated', () => {
    expect(profile).toContain(':key="`profile-language-${locale}`"');
    expect(profile).toContain("const { t, locale } = useI18n()");
  });
});
