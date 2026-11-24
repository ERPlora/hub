// The cash sessions a spec opens: one just opened, once the one left open is closed at what it expects, and after
// the run every one of them gone with its counts and movements.
import { type BrowserContext, expect } from '@playwright/test';

import { A, api, psql } from './helpers';

/** A cash session of 10.00 just opened, once the one left open is closed at what it expects; noted in `opened`. */
export async function freshSession(context: BrowserContext, opened: Set<string>): Promise<string> {
  const current = await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current');
  const left = current.data.session;
  if (left) {
    const closed = await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: left.id, closing_balance: Math.max(left.expected_balance ?? 0, 0) });
    expect(closed.status, JSON.stringify(closed.data)).toBe(200);
  }
  const session = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 1000 });
  expect(session.status, JSON.stringify(session.data)).toBe(201);
  opened.add(session.data.id);
  return session.data.id;
}

/** The sessions `opened`, deleted with their counts and movements. */
export function forgetSessions(opened: Iterable<string>): void {
  const ids = [...opened].map((id) => `'${id}'`).join(',');
  if (!ids) return;
  psql(`delete from cash_register_count where session_id in (${ids})`);
  psql(`delete from cash_register_movement where session_id in (${ids})`);
  psql(`delete from cash_register_session where id in (${ids})`);
}
