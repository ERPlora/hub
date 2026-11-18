// flow: ninguno — FIX tests/e2e (the `rowAction` and `rowActionIcon` helpers of service-helpers.ts; hub#1279, hub#1339)
// `rowAction` runs a row action through its button, or through «⋮» when the row folds its actions. The book's table
// (`DataTable` of `@erplora/ui`) folds them by measuring its box, and after a resize it starts again with every button
// out and folds a step per measurement: a frame or more later. `reservation-book.spec.ts` looked at the row while its
// «Edit» was still out, the table folded it before the click landed, and the click waited for a button that was gone
// until the test's time ran out. These pages stand in for that row, without a stack: one keeps its buttons, one has
// them folded, one folds them the moment the pointer comes to click (the worst order, made certain: the helper has
// already looked) and one loses its button under the press. Each says which action ran. `rowActionIcon` reads the icon
// of an action without running it, on the same rows, and on one that folds «Edit» into «⋮» right after its icon is
// first read, before it is drawn: the fold the click of `rowAction` cannot help with, since nothing is clicked.
import { expect, type Page, test } from '@playwright/test';

import { iconPaint, PAINTED, rowAction, rowActionIcon } from './service-helpers';

/** A row of the table `book` (its hooks as `DataTable.vue` names them) inside a shown page: `buttons`, its «Edit» out;
 *  `folded`, inside «⋮», which opens an `ion-popover` with the entry; `folds`, out until the pointer first moves, when
 *  the row folds it into «⋮» as the table does after a resize; `drops`, out until it is pressed, when the row loses it
 *  and no click comes of the press; `foldsOnRead`, out with its icon not drawn yet until that icon is first read, when
 *  the row folds it right after; `bare`, no actions at all. Like the table's actions cell (`@click.stop`), the row's
 *  actions keep their clicks from bubbling: what says where a click landed has to hear it on its way down. Every
 *  control wears an `ion-icon` the shell registered (`create-outline`, in Ionicons' map): named on the row's button,
 *  handed as its data URL in «⋮», as the table does. `window.ran` lists the actions run. */
const bookRow = (row: 'buttons' | 'folded' | 'folds' | 'drops' | 'foldsOnRead' | 'bare') => `
  <div class="ion-page">
    <div data-testid="book-row" data-id="r1">
      <span>Iris</span>
      <span data-role="actions"></span>
    </div>
  </div>
  <script>
    window.ran = [];
    const SRC = 'data:image/svg+xml;utf8,<svg/>';
    window.Ionicons = { map: new Map([['create-outline', SRC]]) };
    const actions = document.querySelector('[data-role=actions]');
    actions.addEventListener('click', (event) => event.stopPropagation());
    const icon = (place, drawn) => {
      const ion = document.createElement('ion-icon');
      if (place === 'row') ion.name = 'create-outline';
      else ion.icon = SRC;
      const root = ion.attachShadow({ mode: 'open' });
      root.innerHTML = '<div class="icon-inner"><svg width="16" height="16">' + (drawn ? '<path d="M0 0h16v16H0z"/>' : '') + '</svg></div>';
      return ion;
    };
    const control = (testid, label, run, ion) => {
      const button = document.createElement('button');
      button.dataset.testid = testid;
      button.append(ion, label);
      button.addEventListener('click', run);
      return button;
    };
    const fold = () => actions.replaceChildren(menu());
    const edit = () => {
      const ion = icon('row', '${row}' !== 'foldsOnRead');
      if ('${row}' === 'foldsOnRead') {
        const root = ion.shadowRoot;
        Object.defineProperty(ion, 'shadowRoot', { get: () => (setTimeout(fold), root) });
      }
      return control('book-row-r1-edit', 'Edit', () => window.ran.push('edit'), ion);
    };
    const menu = () =>
      control('book-row-r1-menu', '⋮', () => {
        const popover = document.createElement('ion-popover');
        popover.append(control('book-row-r1-edit', 'Edit', () => {
          window.ran.push('edit');
          popover.remove();
        }, icon('menu', true)));
        document.body.append(popover);
      }, icon('row', true));
    actions.replaceChildren(...({ folded: [menu()], bare: [] }['${row}'] ?? [edit()]));
    if ('${row}' === 'folds') document.addEventListener('mousemove', fold, { once: true });
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

test('rowActionIcon reads the icon on the row’s button while the row keeps it out, and never opens «⋮»', async ({ page }) => {
  await page.setContent(bookRow('buttons'));
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toEqual(PAINTED);
  await expect(page.locator('ion-popover')).toHaveCount(0);
  expect(await ran(page)).toEqual([]);
});

test('rowActionIcon opens «⋮» when the row has the action folded, and reads the icon of its entry there', async ({ page }) => {
  await page.setContent(bookRow('folded'));
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toBe('in «⋮»');
  await expect(page.locator('ion-popover [data-testid=book-row-r1-edit]')).toBeVisible();
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toEqual(PAINTED);
  expect(await ran(page)).toEqual([]);
});

// hub#1339
test('rowActionIcon reads the icon in «⋮» when the row folds the button away after its icon was read, before it was drawn', async ({ page }) => {
  await page.setContent(bookRow('foldsOnRead'));
  await expect.poll(() => rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toEqual(PAINTED);
  await expect(page.locator('ion-popover [data-testid=book-row-r1-edit]')).toBeVisible();
  expect(await ran(page)).toEqual([]);
});

test('rowActionIcon says the row shows the action nowhere, instead of waiting for it', async ({ page }) => {
  await page.setContent(bookRow('bare'));
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toBe('not shown');
});

test('rowActionIcon reads an icon the shell never registered as such', async ({ page }) => {
  await page.setContent(bookRow('buttons'));
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'trash-outline')).toEqual({ registered: false, named: false, drawn: true, visible: true });
});

test('rowActionIcon reads an icon the page hides, leaves out of the layout or gives no box as not visible', async ({ page }) => {
  await page.setContent(bookRow('buttons'));
  for (const hiding of ['visibility: hidden', 'display: none', 'display: inline-block; width: 0; height: 0; overflow: hidden']) {
    const style = await page.addStyleTag({ content: `[data-testid=book-row-r1-edit] ion-icon { ${hiding} }` });
    expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline'), hiding).toEqual({ ...PAINTED, visible: false });
    await style.evaluate((tag) => (tag as HTMLStyleElement).remove());
  }
  expect(await rowActionIcon(page, 'book', 'r1', 'edit', 'create-outline')).toEqual(PAINTED);
});

test('iconPaint reads an icon that wears no hook of its own, as a tab’s or a tile’s', async ({ page }) => {
  await page.setContent(bookRow('buttons'));
  await expect.poll(() => iconPaint(page.locator('[data-testid=book-row-r1-edit] ion-icon'), 'create-outline')).toEqual(PAINTED);
});
