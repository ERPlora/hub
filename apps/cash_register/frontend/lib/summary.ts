// The figures of a session (CASH_REGISTER-F11, F16): one list, painted by the detail and printed by the
// X/Z report, so the screen and the paper never say different things. Every amount is the server's; a
// figure the server withholds (a blind count) is left out or «—», never computed here.
import type { SessionOut } from '../operations';
import { formatMoney, formatSignedMoney } from './money';

type Translate = (key: string, named?: Record<string, unknown>) => string;

export interface SummaryItem {
  key: string;
  label: string;
  value: string;
}

/** The figures of `session` in the reader's language; `date` writes a date and time. */
export function summaryItems(session: SessionOut, t: Translate, locale: string, date: (iso: string | null) => string): SummaryItem[] {
  const s = session.summary;
  const closed = session.status === 'closed';
  const money = (cents: number | null) => formatMoney(cents, locale);
  const item = (key: string, value: string): SummaryItem => ({ key, label: t(`cash_register.summary.${key}`), value });
  const closedBy = !closed
    ? '—'
    : session.auto_closed
      ? t('cash_register.summary.closedAuto', { when: date(session.closed_at) })
      : t('cash_register.summary.by', { when: date(session.closed_at), who: session.closed_by });
  const items = [
    item('status', t(`cash_register.status.${session.status}`)),
    item('register', session.register_name || '—'),
    item('opened', t('cash_register.summary.by', { when: date(session.opened_at), who: session.opened_by })),
    item('closed', closedBy),
    item('movements', String(s.movement_count)),
    item('opening', money(s.opening_balance)),
    item('sales', money(s.total_sales)),
  ];
  if (s.cash_sales !== null) {
    items.push(item('cashSales', money(s.cash_sales)), item('cardSales', money(s.card_sales)));
    if ((s.other_sales ?? 0) > 0) items.push(item('otherSales', money(s.other_sales)));
  }
  items.push(
    item('refunds', money(s.total_refunds)),
    item('cashIn', money(s.total_cash_in)),
    item('cashOut', money(s.total_cash_out)),
    item('gifts', money(s.total_gifts)),
    item('expected', money(s.expected_cash)),
    item('counted', closed ? money(s.counted) : '—'),
    item('difference', closed ? formatSignedMoney(s.difference, locale) : '—'),
  );
  if (session.opening_notes) items.push(item('openingNotes', session.opening_notes));
  if (session.closing_notes) items.push(item('closingNotes', session.closing_notes));
  return items;
}
