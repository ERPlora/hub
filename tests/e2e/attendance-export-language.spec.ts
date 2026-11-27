// flow: ATTENDANCE-F10
// The month's CSV reads in the language of whoever exports it: with the Hub in Spanish, Records › «Exportar CSV»
// downloads a file whose header, status and radius are in Spanish, as the invoices' and the products' exports are.
import { readFileSync } from 'node:fs';

import { expect, test } from '@playwright/test';

import { A, api, psql, shown, signedInSpanish } from './helpers';

const TAG = 'E2EAttCsv';
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name = '${TAG}')`;

function cleanup(): void {
  psql(
    [
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name = '${TAG}'`,
    ].join('; '),
  );
}

test.beforeEach(cleanup);
test.afterAll(cleanup);

test('ATTENDANCE-F10: with the Hub in Spanish, the month’s CSV says its header and status in Spanish', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, { width: 1280, height: 860 }, '/attendance/records');
  try {
    const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: TAG, last_name: 'Clock' });
    expect(created.status).toBe(201);
    for (const path of ['/attendance/clock_in', '/attendance/clock_out']) {
      expect((await api(context, A, 'POST', path, { member_id: created.data.id })).status, path).toBe(200);
    }
    await page.reload();

    const download = page.waitForEvent('download');
    await shown(page).locator('[data-testid=attendance-export-csv]').click();
    const text = readFileSync((await (await download).path()) as string, 'utf8');
    expect(text.startsWith('﻿'), 'a BOM, so a spreadsheet reads the accents').toBe(true);
    const [header, ...lines] = text.slice(1).trim().split('\r\n');
    expect(header).toBe(
      'Fecha,Persona,Entrada,Salida,Minutos de pausa,Minutos trabajados,Estado,Entrada dentro del radio,Salida dentro del radio',
    );
    expect(lines.find((line) => line.includes(`${TAG} Clock`))).toContain(',Cerrada,');
  } finally {
    await context.close();
  }
});
