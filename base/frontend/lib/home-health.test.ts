// How a state of the Home's health row looks, shared by the row and by the cards that say the same state elsewhere
// (Printing's «Your printer» in System).
import { describe, expect, it } from 'vitest';

import { HEALTH_PILLS } from './home-health';

describe('HEALTH_PILLS', () => {
  it('paints what works green with a tick, what the person can fix amber with a triangle and what could not be checked grey', () => {
    expect(HEALTH_PILLS).toEqual({
      ok: { tone: 'success', icon: 'ion:checkmark-circle-outline' },
      no_signal: { tone: 'warning', icon: 'ion:warning-outline' },
      not_configured: { tone: 'warning', icon: 'ion:warning-outline' },
      unknown: { tone: 'neutral', icon: 'ion:help-circle-outline' },
    });
  });

  it('cannot be changed by whoever reads it', () => {
    expect(Object.isFrozen(HEALTH_PILLS)).toBe(true);
  });
});
