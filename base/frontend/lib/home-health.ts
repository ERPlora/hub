// How each state of the Home's health row looks: the row and the cards that say the same state elsewhere use this
// one table, so a printer never looks ready in one place and amber in another. The icon gives a shape besides the
// colour; what could not be checked is grey, never green.
import type { StatusPillTone } from '@erplora/ui/components';

import type { HomeHealthState } from '../operations/home';

export interface HealthPill {
  tone: StatusPillTone;
  icon: string;
}

const FIXABLE: HealthPill = Object.freeze({ tone: 'warning', icon: 'ion:warning-outline' });

export const HEALTH_PILLS: Readonly<Record<HomeHealthState, HealthPill>> = Object.freeze({
  ok: Object.freeze({ tone: 'success', icon: 'ion:checkmark-circle-outline' }),
  no_signal: FIXABLE,
  not_configured: FIXABLE,
  unknown: Object.freeze({ tone: 'neutral', icon: 'ion:help-circle-outline' }),
});
