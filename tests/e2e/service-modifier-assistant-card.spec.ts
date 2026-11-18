// hub#676 and hub#672: since hub#416 the assistant's card left out every id its schema does not mark, so «anula ese bono»
// or «borra esa opción» said no voucher and no option. Now each record is named as the Services and Modifiers screens
// show it, read as the person, in their language, never by its id. End to end with the stack's SaaS gateway and the
// e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this
// folder, «El asistente»). Cancelled, nothing changes. What this file creates carries its own prefix (E2ESMC) and goes
// away; the apps it turns on are turned off again.
// flow: SERVICE-F17 SERVICE-F32 MODIFIER-F04 MODIFIER-F05 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql, untilStill } from './helpers';
import { createProduct, post, stamp } from './pricing-helpers';

/** The apps the records need: a business is born with every app off. */
const NEEDED = ['inventory', 'tax', 'customer', 'staff', 'service', 'modifier'];
const PREFIX = 'E2ESMC';
const RUN = stamp();

/** What each screen calls the record, by the language of the card. */
const TITLES = {
  es: { grant: 'Bono vendido', assignment: 'Profesional del servicio', option: 'Opción', link: 'Se aplica a' },
  en: { grant: 'Voucher sold', assignment: 'Professional of a service', option: 'Option', link: 'Applies to' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Deletes what this file created (names and SKUs `E2ESMC…`). */
function cleanUp(): void {
  const named = `like '${PREFIX}%'`;
  const packages = `select id from service_package where name ${named}`;
  const services = `select id from service_service where name ${named}`;
  const groups = `select id from modifier_modifiergroup where name ${named}`;
  const products = `select id from inventory_product where sku ${named}`;
  psql(
    [
      `delete from service_grant where package_id in (${packages})`,
      `delete from service_packageitem where package_id in (${packages})`,
      `delete from service_package where name ${named}`,
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name ${named}`,
      `delete from staff_member where first_name ${named}`,
      `delete from customer_customer where name ${named}`,
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      `delete from modifier_modifiergroup where name ${named}`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku ${named}`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanUp);

/** A haircut Ana performs and a voucher of it sold to Lucía, through each app's API. */
async function aSalon(context: BrowserContext, tag: string) {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: `${PREFIX} Corte ${tag}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: `${PREFIX} Ana ${tag}`, last_name: 'López' });
  const assignment = await post<{ id: string }>(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
    name: `${PREFIX} Lucía ${tag}`,
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const voucher = await post<{ id: string; name: string }>(context, '/service/packages', {
    name: `${PREFIX} Bono ${tag}`,
    items: [{ service_id: service.id, sessions: 5 }],
  });
  const grant = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: customer.id });
  return { service, member, assignment, customer, voucher, grant };
}

/** A group of sauces with an option, hung from a product, through each app's API. */
async function aGroup(context: BrowserContext, tag: string) {
  const group = await post<{ id: string; name: string }>(context, '/modifier/groups', { name: `${PREFIX} Salsas ${tag}` });
  const option = await post<{ id: string; name: string }>(context, '/modifier/options', { group_id: group.id, name: `${PREFIX} Alioli ${tag}` });
  const name = `${PREFIX} Hamburguesa ${tag}`;
  const product = await createProduct(context, name, `${PREFIX}-${tag}`, 900);
  const link = await post<{ id: string }>(context, '/modifier/links/attach', { group_id: group.id, product_id: product.id });
  return { group, option, product: { ...product, name }, link };
}

for (const language of ['es', 'en'] as const) {
  const titles = TITLES[language];

  test(`service-assistant-card — in ${language}, voiding a voucher and removing a professional name which, never by their id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const salon = await aSalon(context, `${RUN}${language}`);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Anula ese bono», a dangerous write: the voucher by its package, its owner and the day it was sold.
    const voided = await datumOf(page, 'service__grant__void', { id: salon.grant.id, reason: 'Sold by mistake' });
    expect(voided.label).toBe(titles.grant);
    const said = String(voided.value);
    expect(said.startsWith(`${salon.voucher.name} · ${salon.customer.name} · `), said).toBe(true);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${titles.grant}: ${said}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-676-service-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quítale ese servicio a Ana»: who does what, by the service and the professional.
    const removed = await datumOf(page, 'service__assignment__remove', { id: salon.assignment.id });
    expect(removed.label).toBe(titles.assignment);
    expect(removed.value).toBe(`${salon.service.name} · ${salon.member.full_name}`);
    await expect(card(page)).toContainText(String(removed.value));
    await cancel(page);

    // Cancelled, nothing changed, and the reads that name them answer by the same routes as any other client.
    const grant = await api<{ status: string; label: string }>(context, A, 'GET', `/service/grants/detail?id=${salon.grant.id}`);
    expect(grant.status, JSON.stringify(grant.data)).toBe(200);
    expect(grant.data.status).toBe('active');
    const assignment = await api<{ is_active: boolean; label: string }>(context, A, 'GET', `/service/assignments/detail?id=${salon.assignment.id}`);
    expect(assignment.status, JSON.stringify(assignment.data)).toBe(200);
    expect(assignment.data.is_active).toBe(true);
    await context.close();
  });

  test(`modifier-assistant-card — in ${language}, deleting an option and detaching a group name which, never by their id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const sauces = await aGroup(context, `${RUN}${language}`);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra el alioli», a dangerous write: the option by its name and its group, as two groups may have one with that name.
    const deleted = await datumOf(page, 'modifier__option__delete', { id: sauces.option.id });
    expect(deleted.label).toBe(titles.option);
    expect(deleted.value).toBe(`${sauces.option.name} (${sauces.group.name})`);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${titles.option}: ${String(deleted.value)}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-672-modifier-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quita las salsas de la hamburguesa»: the link by its group and what it hangs from.
    const detached = await datumOf(page, 'modifier__link__detach', { id: sauces.link.id });
    expect(detached.label).toBe(titles.link);
    expect(detached.value).toBe(`${sauces.group.name} · ${sauces.product.name}`);
    await expect(card(page)).toContainText(String(detached.value));
    await cancel(page);

    // Cancelled, nothing changed: the option and the link are still there.
    const option = await api<{ id: string }>(context, A, 'GET', `/modifier/options/detail?id=${sauces.option.id}`);
    expect(option.status, JSON.stringify(option.data)).toBe(200);
    const link = await api<{ id: string }>(context, A, 'GET', `/modifier/links/detail?id=${sauces.link.id}`);
    expect(link.status, JSON.stringify(link.data)).toBe(200);
    await context.close();
  });
}
