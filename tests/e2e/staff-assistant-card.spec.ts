// hub#495: since hub#416 the assistant's card left out every id its schema does not mark, so «approve Ana's holiday» or
// «delete that schedule» said no person, no schedule and no time off. Now each record of Staff is named as its screens
// show it, read as the person, in their language, never by its id; a schedule says whose it is and a time off whose, of
// what kind and which days. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). Cancelled, nothing
// changes. What this file creates carries its own prefix (E2ESAC) and goes away; the app it turns on is turned off again.
// flow: STAFF-F02 STAFF-F04 STAFF-F05 STAFF-F07 STAFF-F15 STAFF-F18 STAFF-F19 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql, untilStill } from './helpers';
import { post, stamp } from './pricing-helpers';

/** A business is born with every app off. */
const NEEDED = ['staff'];
const PREFIX = 'E2ESAC';
const RUN = stamp();
const WEEK = [{ weekday: 0, start_time: '09:00', end_time: '17:00' }];

/** What each screen calls the record and how a day off reads, by the language of the card. */
const WORDS = {
  es: { member: 'Miembro del personal', role: 'Rol', schedule: 'Horario', timeOff: 'Ausencia', vacation: 'Vacaciones', days: '2 nov 2026 – 5 nov 2026' },
  en: { member: 'Staff member', role: 'Role', schedule: 'Schedule', timeOff: 'Time off', vacation: 'Vacation', days: 'Nov 2, 2026 – Nov 5, 2026' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Deletes what this file created (first names and role names `E2ESAC…`). */
function cleanUp(): void {
  const named = `like '${PREFIX}%'`;
  const members = `select id from staff_member where first_name ${named}`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name ${named}`,
      `delete from staff_role where name ${named}`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanUp);

/** A role, someone who holds it, their schedule and their holiday, through Staff's own API. */
async function aTeam(context: BrowserContext, tag: string) {
  const role = await post<{ id: string; name: string }>(context, '/staff/roles', { name: `${PREFIX} Colorista ${tag}` });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: `${PREFIX} Ana ${tag}`,
    last_name: 'López',
    role_id: role.id,
  });
  const schedule = await post<{ id: string; name: string }>(context, '/staff/schedules', {
    member_id: member.id,
    name: `${PREFIX} Verano`,
    days: WEEK,
  });
  const timeOff = await post<{ id: string; status: string }>(context, '/staff/time_off', {
    member_id: member.id,
    leave_type: 'vacation',
    start_date: '2026-11-02',
    end_date: '2026-11-05',
  });
  return { role, member, schedule, timeOff };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`staff-assistant-card — in ${language}, a write of Staff says which person, role, schedule or time off, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const team = await aTeam(context, `${RUN}${language}`);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra ese horario», a dangerous write: its title and whose it is, in every size.
    const scheduleName = `${team.member.full_name} · ${team.schedule.name}`;
    const removed = await datumOf(page, 'staff__schedule__delete', { id: team.schedule.id });
    expect([removed.label, removed.value]).toEqual([words.schedule, scheduleName]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.schedule}: ${scheduleName}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-495-schedule-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Da de baja a Ana», another dangerous one: the person.
    const left = await datumOf(page, 'staff__member__deactivate', { id: team.member.id });
    expect([left.label, left.value]).toEqual([words.member, team.member.full_name]);
    await expect(card(page)).toContainText(`${words.member}: ${team.member.full_name}`);
    await cancel(page);

    // «Aprueba sus vacaciones»: whose, of what kind and which days, in the person's language.
    const timeOffName = `${team.member.full_name} · ${words.vacation} · ${words.days}`;
    const approved = await datumOf(page, 'staff__time_off__approve', { id: team.timeOff.id });
    expect([approved.label, approved.value]).toEqual([words.timeOff, timeOffName]);
    await expect(card(page)).toContainText(timeOffName);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(timeOffName);
      await untilStill(page);
      await capture(page, `hub-495-time-off-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // The role of a record and the people of a batch, each by the role's name (the case the issue names).
    const retitled = await datumOf(page, 'staff__member__update', { id: team.member.id, role_id: team.role.id }, 'role_id');
    expect([retitled.label, retitled.value]).toEqual([words.role, team.role.name]);
    await cancel(page);
    const batch = await datumOf(page, 'staff__member__bulk_create', {
      members: [{ first_name: `${PREFIX} Bea ${RUN}`, last_name: 'Ruiz', role_id: team.role.id }],
    }, 'members');
    expect(batch.value).toEqual([expect.objectContaining({ role_id: team.role.name })]);
    await cancel(page);

    // Cancelled, nothing changed.
    const after = await api<{ status: string }>(context, A, 'GET', `/staff/time_off/detail?id=${team.timeOff.id}`);
    expect(after.status, JSON.stringify(after.data)).toBe(200);
    expect(after.data.status).toBe('pending');
    const schedule = await api(context, A, 'GET', `/staff/schedules/detail?id=${team.schedule.id}`);
    expect(schedule.status, JSON.stringify(schedule.data)).toBe(200);
    await context.close();
  });
}
