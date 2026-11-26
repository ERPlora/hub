// The long Spanish texts screens-text-fits.spec.ts puts in the business before it walks the screens, through each
// app's own API, and how it takes them away: names as long as real ones, and a morning of the agenda booked with them.
import { type BrowserContext, expect } from '@playwright/test';

import { aMonday, salonCleanUpWhere } from './appointment-helpers';
import { cardDeletes } from './customer-helpers';
import { A, api, psql } from './helpers';
import { createProduct } from './inventory-helpers';
import { post } from './service-helpers';

/** The booked day: a Monday six weeks ahead, open from 09:00 to 20:00. */
export const BOOKED_DAY = aMonday(1);

const CUSTOMERS = ['Lucía Gómez Santamaría', 'Marina Sotelo Barrientos', 'Inés Martínez de la Fuente', 'Rosa Díaz Carrasco', 'Carmen Olmedo Villanueva'];
const SERVICES = [
  { name: 'Corte de mujer con lavado y peinado', duration_minutes: 30 },
  { name: 'Mechas balayage con matiz y tratamiento', duration_minutes: 45 },
];
const STAFF = [
  { first_name: 'María del Carmen', last_name: 'Fernández-Villaverde' },
  { first_name: 'Ana Belén', last_name: 'Rodríguez Montenegro' },
];
const OPEN_DAY = 'Apertura de los lunes por la mañana';
/** Each booking: the customer, the service and the professional (their place above) and its time. */
const BOOKINGS = [
  [0, 0, 0, '10:00'],
  [1, 1, 0, '10:30'],
  [2, 0, 0, '11:15'],
  [3, 1, 1, '10:00'],
  [4, 0, 1, '10:45'],
] as const;
const CATEGORY = 'Entrantes y raciones para compartir';
const PRODUCT = 'Croquetas caseras de jamón ibérico de bellota';
const ZONE = 'Terraza cubierta del patio interior';

const quoted = (names: string[]): string => names.map((name) => `'${name}'`).join(', ');
const SALON_NAMES = `in (${quoted([...CUSTOMERS, ...SERVICES.map((s) => s.name), ...STAFF.map((s) => s.first_name), OPEN_DAY])})`;

/** Takes away what `seedLongTexts` puts, also what a run that fell left behind. */
export async function removeLongTexts(context: BrowserContext): Promise<void> {
  psql(
    [
      ...salonCleanUpWhere(SALON_NAMES),
      ...cardDeletes(`select id from customer_customer where name in (${quoted(CUSTOMERS)})`),
      `delete from table_table where zone_id in (select id from table_zone where name = '${ZONE}')`,
      `delete from table_zone where name = '${ZONE}'`,
    ].join('; '),
  );
  for (const [list, remove, name] of [
    ['/inventory/products', '/inventory/products/delete', PRODUCT],
    ['/inventory/categories', '/inventory/categories/delete', CATEGORY],
  ]) {
    const rows = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `${list}?limit=100&search=${encodeURIComponent(name)}`);
    for (const row of rows.data.rows.filter((r) => r.name === name)) {
      expect((await api(context, A, 'POST', remove, { id: row.id })).status, `${remove} ${name}`).toBeLessThan(300);
    }
  }
}

/** The salon's long names, its open day and its morning of appointments. */
async function seedSalon(context: BrowserContext): Promise<void> {
  const customers = [];
  for (const name of CUSTOMERS) {
    customers.push(await post<{ id: string }>(context, '/customer/customers', { name, phone: `6${String(Math.random()).slice(2, 10)}` }));
  }
  const services = [];
  for (const service of SERVICES) {
    services.push(await post<{ id: string }>(context, '/service/services', { ...service, price: 3500, tax_category_key: 'service.generic' }));
  }
  const members = [];
  for (const member of STAFF) {
    const made = await post<{ id: string }>(context, '/staff/members', member);
    for (const service of services) await post(context, '/service/assignments/assign', { service_id: service.id, member_id: made.id }, 200);
    members.push(made);
  }
  const intervals = [{ open_time: '09:00', close_time: '20:00' }];
  await post(context, '/schedule/special_days', { date: BOOKED_DAY, name: OPEN_DAY, is_closed: false, intervals });
  for (const [customer, service, member, time] of BOOKINGS) {
    await post(context, '/appointment/appointments', {
      customer_id: customers[customer].id,
      services: [{ service_id: services[service].id }],
      staff_id: members[member].id,
      start: `${BOOKED_DAY}T${time}`,
    });
  }
}

/** The restaurant's long names: a category with its product, and a zone with a table. */
async function seedRestaurant(context: BrowserContext): Promise<void> {
  const category = await post<{ id: string }>(context, '/inventory/categories', { name: CATEGORY });
  await createProduct(context, { name: PRODUCT, sku: `TXT-${Date.now().toString(36)}`, category_ids: [category.id] });
  const zone = await post<{ id: string }>(context, '/table/zones', { name: ZONE });
  await post(context, '/table/tables', { zone_id: zone.id, number: '12', capacity: 6 });
}

/** Puts the long texts in the business at `A`, its apps on, after taking away any a run before left. */
export async function seedLongTexts(context: BrowserContext): Promise<void> {
  await removeLongTexts(context);
  await seedSalon(context);
  await seedRestaurant(context);
}
