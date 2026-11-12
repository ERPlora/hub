// flow: ninguno — FIX tests/e2e (the `rowAction` helper of service-helpers.ts; hub#1279)
// `rowAction` runs a row action through its button, or through «⋮» when the row folds its actions. The book's table
// (`DataTable` of `@erplora/ui`) folds them by measuring its box, and after a resize it starts again with every button
// out and folds a step per measurement: a frame or more later. `reservation-book.spec.ts` looked at the row while its
// «Edit» was still out, the table folded it before the click landed, and the click waited for a button that was gone
// until the test's time ran out. These pages stand in for that row, without a stack: one keeps its buttons, one has
// them folded, one folds them the moment the pointer comes to click (the worst order, made certain: the helper has
// already looked) and one loses its button under the press. Each says which action ran.
import { expect, type Page, test } from '@playwright/test';

import { rowAction } from './service-helpers';

/** A row of the table `book` (its hooks as `DataTable.vue` names them) inside a shown page: `buttons`, its «Edit» out;
 *  `folded`, inside «⋮», which opens an `ion-popover` with the entry; `folds`, out until the pointer first moves, when
 *  the row folds it into «⋮» as the table does after a resize; `drops`, out until it is pressed, when the row loses it
 *  and no click comes of the press. `window.ran` lists the actions run. */
const bookRow = (row: 'buttons' | 'folded' | 'folds' | 'drops') => `
  <div class="ion-page">
    <div data-testid="book-row" data-id="r1">
      <span>Iris</span>
      <span data-role="actions"></span>
    </div>
  </div>
  <script>
    window.ran = [];
    const actions = document.querySelector('[data-role=actions]');
    const control = (testid, label, run) => {
      const button = document.createElement('button');
      button.dataset.testid = testid;
      button.textContent = label;
      button.addEventListener('click', run);
      return button;
    };
    const edit = () => control('book-row-r1-edit', 'Edit', () => window.ran.push('edit'));
    const menu = () =>
      control('book-row-r1-menu', '⋮', () => {
        const popover = document.createElement('ion-popover');
        popover.append(control('book-row-r1-edit', 'Edit', () => {
          window.ran.push('edit');
          popover.remove();
        }));
        document.body.append(popover);
      });
    actions.replaceChildren('${row}' === 'folded' ? menu() : edit());
    if ('${row}' === 'folds') document.addEventListener('mousemove', () => actions.replaceChildren(menu()), { once: true });
    if ('${row}' === 'drops') document.addEventListener('pointerdown', () => actions.replaceChildren(), { once: true });
  </script>`;

const ran = (page: Page) => page.evaluate(() => (window as Window & { ran?: string[] }).ran);

test('rowAction runs the action through the row’s button while the row keeps it out, and never opens «⋮»', async ({ page }) => {
  await page.setContent(bookRow('buttons'));
  await rowAction(page, 'book', 'r1', 'edit');
  expect(await ran(page)).toEqual(['edit']);
  await expect(page.locator('ion-popover')).toHaveCount(0);
});

test('rowAction runs the action through «⋮» when the row has it folded', async ({ page }) => {
  await page.setContent(bookRow('folded'));
  await rowAction(page, 'book', 'r1', 'edit');
  expect(await ran(page)).toEqual(['edit']);
});

// hub#1279
test('rowAction runs the action once when the row folds it into «⋮» after the helper looked and before the click lands', async ({ page }) => {
  await page.setContent(bookRow('folds'));
  await rowAction(page, 'book', 'r1', 'edit');
  expect(await ran(page)).toEqual(['edit']);
});

test('rowAction says so when its click landed on neither the button nor «⋮», instead of waiting for either', async ({ page }) => {
  await page.setContent(bookRow('drops'));
  await expect(rowAction(page, 'book', 'r1', 'edit')).rejects.toThrow('rowAction book-row-r1-edit: the click landed on nothing, neither the button nor «⋮»');
  expect(await ran(page)).toEqual([]);
});
