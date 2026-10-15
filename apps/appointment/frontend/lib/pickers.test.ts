// The searches behind the booking panel's pickers (APPOINTMENT-F01): the bookable services of the catalog
// (Services), with their length and price kept for the panel; and the professionals who may do every
// service chosen — the active, bookable ones assigned to it, or the whole bookable team for a service
// nobody is assigned to (the diary's rule). Each app's list is read through its own operations.
import { describe, expect, it, vi } from 'vitest';

import { eligibleStaff, ownTerms, type ServiceFacts, searchBookableServices } from './pickers';

function client(answers: Record<string, (input: Record<string, unknown>) => unknown>) {
  const call = vi.fn(async (op: string, input: Record<string, unknown>) => answers[op](input));
  return { client: { api: { call } } as never, call };
}

const sale = (id: string, name: string, extra = {}) => ({
  id,
  name,
  price: 2000,
  duration_minutes: 30,
  is_bookable: true,
  ...extra,
});

describe('searchBookableServices', () => {
  it('offers the bookable services of the catalog, keeping their length and price', async () => {
    const { client: api, call } = client({
      'service.service.list_for_sale': () => ({
        rows: [sale('c1', 'Haircut'), sale('c2', 'Colour', { is_bookable: false }), sale('c3', 'Beard', { price: 950, duration_minutes: 15 })],
      }),
    });
    const facts = new Map<string, ServiceFacts>();
    const options = await searchBookableServices(api, 'en', facts)(' cut ');
    expect(call).toHaveBeenCalledWith('service.service.list_for_sale', { search: 'cut', limit: 20 });
    expect(options).toEqual([
      { id: 'c1', label: 'Haircut', hint: '30 min · €20.00' },
      { id: 'c3', label: 'Beard', hint: '15 min · €9.50' },
    ]);
    expect(facts.get('c3')).toEqual({ name: 'Beard', minutes: 15, price: 950 });
  });
});

describe('eligibleStaff', () => {
  const team = { rows: [{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }] };

  it('offers the bookable team when no service is chosen', async () => {
    const { client: api, call } = client({ 'staff.member.list': () => team });
    expect(await eligibleStaff(api, [], '')).toEqual([
      { id: 's1', label: 'Ana López' },
      { id: 's2', label: 'Bea Ruiz' },
    ]);
    expect(call).toHaveBeenCalledWith('staff.member.list', { status: 'active', is_bookable: true, limit: 100 });
  });

  it('keeps who may do every service: the assigned ones, or everybody for a service nobody is assigned to', async () => {
    const { client: api } = client({
      'staff.member.list': () => team,
      'service.assignment.eligible': (input) => ({
        rows: input.service_id === 'colour' ? [{ member_id: 's2', full_name: 'Bea Ruiz' }] : [],
      }),
    });
    expect(await eligibleStaff(api, ['cut', 'colour'], 'b')).toEqual([{ id: 's2', label: 'Bea Ruiz' }]);
    expect(await eligibleStaff(api, ['cut'], '')).toHaveLength(2);
  });
});

describe('ownTerms', () => {
  it('the professional’s own minutes and price for each service she has a row for in Services', async () => {
    const { client: api, call } = client({
      'service.assignment.eligible': (input) => ({
        rows:
          input.service_id === 'cut'
            ? [
                { member_id: 's1', duration: 45, price: 2500 },
                { member_id: 's2', duration: 30, price: 2000 },
              ]
            : [],
      }),
    });
    expect(await ownTerms(api, 's1', ['cut', 'colour'])).toEqual(new Map([['cut', { minutes: 45, price: 2500 }]]));
    expect(call).toHaveBeenCalledWith('service.assignment.eligible', { service_id: 'colour', limit: 100 });
    expect(await ownTerms(api, 's9', ['cut'])).toEqual(new Map());
  });
});
