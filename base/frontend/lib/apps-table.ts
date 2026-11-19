// What the Apps table offers on each row: the switch that turns an app on or off and the actions beside it. Pure: the
// page hands over who reads it and the change on its way, and turns what is pressed into the server's operations.
import type { DataTableAction, DataTableColumnToggle } from '@erplora/ui/components';

import type { AppRow } from '../operations/apps';
import { canOpen, canRetry, canTurnOff, canTurnOn } from './apps';

export interface AppsTableState {
  t: (key: string, values?: Record<string, unknown>) => string;
  /** Who runs the business: turns apps on and off. */
  mayManage: boolean;
  /** Who runs the business, on the web: buys on erplora.com. */
  mayBuy: boolean;
  /** The app whose change is on its way: no other starts meanwhile. */
  pending: string | null;
}

/** On while the business wants the app (on, or being set up); a failed one is off until it is retried. */
const wanted = (app: AppRow): boolean => app.state === 'on' || app.state === 'creating';
const waitsForAnother = (state: AppsTableState, app: AppRow): boolean => state.pending !== null && state.pending !== app.id;

/** Why a row's switch cannot move, or what went wrong: a refusal and a failure only for whoever runs the business,
 *  where a paid app is bought for anyone who cannot buy it here. */
function whyOf(state: AppsTableState, app: AppRow): string | null {
  if (state.mayManage && app.refusal) return app.refusal;
  if (state.mayManage && app.state === 'failed') return state.t('base.appBlocked.failed.heading', { app: app.name });
  if (app.state === 'blocked' && !state.mayBuy) return state.t('base.appsPage.buyWhere');
  return null;
}

/** The switch of the state column, for whoever runs the business. */
export function appSwitch(state: AppsTableState): DataTableColumnToggle<AppRow> {
  return {
    checked: wanted,
    label: (row) => state.t(wanted(row) ? 'base.appsPage.toggle.labelOn' : 'base.appsPage.toggle.labelOff', { app: row.name }),
    disabled: (row) => waitsForAnother(state, row) || !(canTurnOn(row) || canTurnOff(row) || canRetry(row)),
    busy: (row) => state.pending === row.id || row.state === 'creating',
    busyLabel: state.t('base.appsPage.toggle.busy'),
    hidden: () => !state.mayManage,
    note: (row) => whyOf(state, row),
    noteTone: (row) => (row.state === 'failed' && !row.refusal ? 'danger' : 'muted'),
  };
}

/** «Open»; «Upgrade plan» and «Retry», which keep their text; and giving up an app still being set up, or one that
 *  could not be, which its switch cannot say. */
export function appActions(state: AppsTableState): DataTableAction<AppRow>[] {
  const waiting = {
    loading: (row: AppRow) => state.pending === row.id,
    disabled: (row: AppRow) => waitsForAnother(state, row),
  };
  return [
    { id: 'open', label: state.t('base.appsPage.open'), icon: 'ion:open-outline', color: 'primary', pinned: true, hidden: (row) => !canOpen(row) },
    {
      id: 'plans',
      label: state.t('base.appsPage.buy'),
      icon: 'ion:storefront-outline',
      color: 'primary',
      pinned: true,
      showLabel: true,
      hidden: (row) => !state.mayBuy || row.state !== 'blocked',
    },
    {
      id: 'retry',
      label: state.t('base.appsPage.toggle.retry'),
      icon: 'ion:refresh-outline',
      color: 'primary',
      pinned: true,
      showLabel: true,
      hidden: (row) => !state.mayManage || !canRetry(row),
      ...waiting,
    },
    {
      id: 'off',
      label: state.t('base.appsPage.toggle.off'),
      icon: 'ion:close-circle-outline',
      menuOnly: true,
      hidden: (row) => !state.mayManage || !canTurnOff(row) || (row.state !== 'creating' && row.state !== 'failed'),
      ...waiting,
    },
  ];
}
