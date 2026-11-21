import { afterEach, describe, expect, it, vi } from 'vitest';

import { KIND_TONE, releaseDay } from './release-notes';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('releaseDay', () => {
  it('says the day of a note short, in the person language', () => {
    expect(releaseDay('2026-11-19', 'en')).toBe('Nov 19, 2026');
    expect(releaseDay('2026-11-19', 'es')).toBe('19 nov 2026');
  });

  it('is the same day on a device west of Greenwich, never the day before', () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
    expect(releaseDay('2026-01-01', 'en')).toBe('Jan 1, 2026');
  });
});

describe('KIND_TONE', () => {
  it('gives each kind of note its own colour', () => {
    expect(KIND_TONE).toEqual({ new: 'success', improved: 'info', fixed: 'neutral' });
  });
});
