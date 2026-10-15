// The searches behind the booking panel's pickers (`Combo` of @erplora/ui): each asks the server for what
// the person types and turns every row into an option. The required apps' lists are read through their
// own operations (Services, Staff), never their models.
//   - A service: the bookable ones of the catalog (`service.service.list_for_sale`), 20 at a time, with
//     «30 min · €20.00» as a hint; its length and price are kept in `facts` for the panel's minutes.
//   - A professional: the active, bookable team (`staff.member.list`), narrowed, for every service
//     chosen, to whoever is assigned to it (`service.assignment.eligible`); a service nobody is assigned
//     to leaves the whole team (the diary's rule, as the server applies it).
//   - Her terms: the minutes and price she does each service at (`service.assignment.eligible`: her own,
//     or the catalog's), which the server books; a service without her row keeps the catalog's.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { formatMoney } from './format';

const PAGE = 20;
const TEAM = 100;

/** What the panel needs of a service it offered. */
export interface ServiceFacts {
  name: string;
  minutes: number;
  price: number;
}

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});

export function searchBookableServices(client: LiveClient, locale: string, facts: Map<string, ServiceFacts>): ComboSearch {
  return async (query) => {
    const page = await client.api.call('service.service.list_for_sale', { ...search(query), limit: PAGE });
    return page.rows
      .filter((row) => row.is_bookable)
      .map((row) => {
        facts.set(row.id, { name: row.name, minutes: row.duration_minutes, price: row.price });
        return { id: row.id, label: row.name, hint: `${row.duration_minutes} min · ${formatMoney(row.price, locale)}` };
      });
  };
}

/** The professionals who may do every service of `serviceIds`, matching `query`. */
export async function eligibleStaff(client: LiveClient, serviceIds: readonly string[], query: string): Promise<ComboOption[]> {
  const team = await client.api.call('staff.member.list', { ...search(query), status: 'active', is_bookable: true, limit: TEAM });
  let allowed = null as Set<string> | null;
  for (const serviceId of serviceIds) {
    const assigned = await client.api.call('service.assignment.eligible', { service_id: serviceId, limit: TEAM });
    if (!assigned.rows.length) continue;
    const ids = new Set(assigned.rows.map((row) => row.member_id));
    allowed = allowed ? new Set([...allowed].filter((id) => ids.has(id))) : ids;
  }
  return team.rows.filter((row) => !allowed || allowed.has(row.id)).map((row) => ({ id: row.id, label: row.full_name }));
}

/** The minutes and price of a service as one professional does it. */
export interface Terms {
  minutes: number;
  price: number;
}

/** What `memberId` does each of `serviceIds` at, for the services Services lists her for. */
export async function ownTerms(client: LiveClient, memberId: string, serviceIds: readonly string[]): Promise<Map<string, Terms>> {
  const out = new Map<string, Terms>();
  for (const serviceId of serviceIds) {
    const assigned = await client.api.call('service.assignment.eligible', { service_id: serviceId, limit: TEAM });
    const mine = assigned.rows.find((row) => row.member_id === memberId);
    if (mine) out.set(serviceId, { minutes: mine.duration, price: mine.price });
  }
  return out;
}
