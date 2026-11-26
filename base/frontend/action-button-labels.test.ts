// An action button whose icon says it alone is that icon: its label is its accessible name and its title on hover,
// never text beside it. Only a button whose icon does not say what it does paints its words («Save», «Try again»),
// and a datum (an amount, a count) stays beside its icon. This guard reads the templates of base and of every app:
// an `ion-button` that paints text beside an icon fails unless it is listed below with why, and so does an exception
// that is no longer there (the list only shrinks). A button that is only its icon carries its name (`aria-label`) and
// its `title`, and puts the icon in `slot="icon-only"`, which is what gives it the common square to hit (one that sizes
// its own square is listed with why).
import { readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';
import { parse } from 'vue/compiler-sfc';

import { findingsByApp, HUB, hubFrontends } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

const RETRY = '«Try again» has no icon of its own (a refresh arrow reloads)';
const SUBMIT = 'the submit of a form says its consequence';
const NAVIGATION = 'a link to another screen, not an action';
const DATUM = 'what it shows beside its icon is a datum, not a label';
const CLOCK = 'the clock’s full-width call to action: its icon alone does not say it';
const STOCK = 'a stock movement: no icon says it alone';
const KDS_STEP = 'the ticket’s full-width step: «Ready» and «Served» would be two check marks side by side on the board';

/** `<path from the hub>#<data-testid, or the first i18n key it paints>` → why it paints text beside its icon. */
const LABELLED_BUTTONS: Readonly<Record<string, string>> = {
  'apps/attendance/frontend/pages/ClockPage.vue#attendance-break-end': CLOCK,
  'apps/attendance/frontend/pages/ClockPage.vue#attendance-break-start': CLOCK,
  'apps/attendance/frontend/pages/ClockPage.vue#attendance-clock-in': CLOCK,
  'apps/attendance/frontend/pages/ClockPage.vue#attendance-clock-out': CLOCK,
  'apps/attendance/frontend/pages/ClockPage.vue#attendance-clock-retry': RETRY,
  'apps/attendance/frontend/pages/SettingsPage.vue#attendance-settings-use-location':
    'a globe names the web: no icon says «Use my current location»',
  'apps/cash_register/frontend/components/SettingsCard.vue#cash-register-settings-save': SUBMIT,
  'apps/combo/frontend/components/CourseCard.vue#`${prefix}-bulk`': 'beside «Add» (one choice), a «+» does not say «Add several»',
  'apps/combo/frontend/pages/MenuBuilderPage.vue#combo-builder-back': NAVIGATION,
  'apps/customer/frontend/components/CustomerSearch.vue#customer-search-quick-add': 'it names the customer it creates from what was typed',
  'apps/customer/frontend/components/CustomerSearch.vue#customer-search-trigger':
    'a picker that shows the customer chosen (a datum), or «Assign customer» while there is none, as a field does',
  'apps/flow/frontend/components/ConditionRows.vue#`${testid}-add`': 'the step holds another «+» («Insert data»): this one keeps its words',
  'apps/flow/frontend/components/FlowGallery.vue#flow-gallery-guide': NAVIGATION,
  'apps/flow/frontend/components/HistoryPanel.vue#`flow-run-retry-${run.id}`':
    '«Resume from the step that failed» has no icon of its own (a refresh arrow reloads)',
  'apps/flow/frontend/components/RecipeShelf.vue#`flow-recipe-restore-${recipe.ref}`':
    '«Restore the factory one» has no icon of its own (a refresh arrow reloads)',
  'apps/flow/frontend/pages/GuidePage.vue#flow-guide-back': NAVIGATION,
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-back-on-sale': 'no icon says «Back on sale»',
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-count': STOCK,
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-print-label':
    'a tag does not say «Print barcode», and a printer would read as printing the product',
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-receive': STOCK,
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-sold-out': 'no icon says «Sold out»',
  'apps/inventory/frontend/components/ProductDetailModal.vue#inventory-product-detail-write-off': STOCK,
  'apps/kitchen/frontend/components/KdsTicketActions.vue#`kitchen-card-${id}-bump`': KDS_STEP,
  'apps/kitchen/frontend/components/KdsTicketActions.vue#`kitchen-card-${id}-served`': KDS_STEP,
  'apps/printing/frontend/components/DiscoverPrintersModal.vue#printing-discover-again': RETRY,
  'apps/sale/frontend/components/backoffice/SettingsForm.vue#sale-settings-save': SUBMIT,
  'apps/sale/frontend/components/checkout/CheckoutFoot.vue#sale-checkout-check-sales': NAVIGATION,
  'apps/sale/frontend/components/checkout/CheckoutFoot.vue#sale-checkout-open-drawer':
    'the cash icon is the charge’s own: alone it does not say «Open a cash session»',
  'apps/sale/frontend/components/pos/CartFooter.vue#pos-charge': `${DATUM}: the amount to charge`,
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-staff`': `${DATUM}: who the line is for`,
  'apps/sale/frontend/components/pos/KitchenSendBar.vue#pos-kitchen-send': `${DATUM}: how many dishes are waiting`,
  'apps/sale/frontend/components/pos/PosItemTile.vue#testid': 'a tile of the till, not an action button',
  'apps/sale/frontend/components/pos/ProductGrid.vue#pos-grid-more': 'a chevron reads as «expand», not «Load more»',
  'apps/verifactu/frontend/components/RepresentationGrant.vue#`verifactu-grant-choose-${name}`': 'no icon says which file it chooses',
  'apps/verifactu/frontend/components/RepresentationGrant.vue#verifactu-grant-download':
    'fills the form in with the signer’s data and downloads it: a submit says its consequence',
  'apps/verifactu/frontend/components/RepresentationGrant.vue#verifactu-grant-resend': '«Send again» has no icon of its own (a refresh arrow reloads)',
  'apps/verifactu/frontend/pages/ConfigPage.vue#verifactu-config-cert-choose': 'a key names the certificate, not choosing its file',
  'apps/website/frontend/components/ShareDialog.vue#`${one.testid}-png`': 'the format tells the two downloads apart',
  'apps/website/frontend/components/ShareDialog.vue#`${one.testid}-svg`': 'the format tells the two downloads apart',
  'apps/website/frontend/pages/WebsitePage.vue#website-publish': 'publishing puts the site online: a cloud with an arrow reads as uploading a file',
  'base/frontend/components/ChangeBusinessButton.vue#change-business-button': 'in a menu, an option carries its icon and its words',
  'base/frontend/components/HomeHealthRow.vue#home-health-system': NAVIGATION,
  'base/frontend/components/settings/BusinessPanel.vue#business-change': `${NAVIGATION} (erplora.com)`,
  'base/frontend/pages/FilesPage.vue#files-new-folder': 'a folder alone names the folders, and no icon of the Hub says «New folder»',
};

/** `<path from the hub>#<data-testid>` → why that button that is only its icon sizes its own square. */
const OWN_SQUARE: Readonly<Record<string, string>> = {
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-discount`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-gift`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-mark`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-note`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-remove`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/CartLine.vue#`pos-line-${line.id}-void`': 'the cart line’s 44 px buttons and their icons',
  'apps/sale/frontend/components/pos/SpeakKey.vue#pos-speak': 'a key of the till, sized with the others',
};

const ICON_ALONE =
  'an action button whose icon says it alone shows the icon alone, named by `aria-label` and `title`: move its text ' +
  'there and its icon to slot="icon-only", or, if no icon says the action (or the text is a datum), add it to ' +
  'LABELLED_BUTTONS with the reason';
const NAMED_SQUARE =
  'a button that is only its icon carries `aria-label` and `title` with its label, and its icon in slot="icon-only" ' +
  '(or, if it sizes its own square, it is in OWN_SQUARE with the reason)';

const ELEMENT = 1;
const TEXT = 2;
const INTERPOLATION = 5;
const ATTRIBUTE = 6;
const DIRECTIVE = 7;

const BUTTONS = new Set(['ion-button', 'IonButton']);
const ICONS = new Set(['HubIcon', 'ion-icon', 'IonIcon']);

interface TemplateProp {
  type: number;
  name: string;
  value?: { content: string };
  arg?: { content: string };
  exp?: { content: string };
}

interface TemplateNode {
  type: number;
  tag?: string;
  content?: string;
  props?: TemplateProp[];
  children?: TemplateNode[];
  loc: { start: { line: number }; source: string };
}

/** An `ion-button` of a template that holds an icon. */
export interface IconButton {
  line: number;
  /** Its `data-testid` (bound or not), else the first i18n key it paints, else `?`. */
  id: string;
  /** Whether it paints text (words or a datum) beside its icon. */
  painted: boolean;
  /** Whether it carries both `aria-label` and `title`. */
  named: boolean;
  /** Whether its icon sits in `slot="icon-only"`. */
  slotted: boolean;
}

/** The static value of the attribute `name` of `node`, or the source of its binding. */
function propOf(node: TemplateNode, name: string): string | undefined {
  for (const prop of node.props ?? []) {
    if (prop.type === ATTRIBUTE && prop.name === name) return prop.value?.content ?? '';
    if (prop.type === DIRECTIVE && prop.name === 'bind' && prop.arg?.content === name) return prop.exp?.content ?? '';
  }
  return undefined;
}

/** The elements under `node` (itself included), depth first. */
function* elements(node: TemplateNode): Generator<TemplateNode> {
  if (node.type === ELEMENT) yield node;
  for (const child of node.children ?? []) yield* elements(child);
}

/** Whether `node` paints text: words or an interpolation outside its icons. */
function paints(node: TemplateNode): boolean {
  if (node.type === TEXT) return (node.content ?? '').trim() !== '';
  if (node.type === INTERPOLATION) return true;
  if (node.type !== ELEMENT || ICONS.has(node.tag ?? '')) return false;
  return (node.children ?? []).some(paints);
}

function iconButton(button: TemplateNode, icons: TemplateNode[]): IconButton {
  const key = /\bt\(\s*'([^']+)'/.exec(button.loc.source)?.[1];
  return {
    line: button.loc.start.line,
    id: propOf(button, 'data-testid') ?? key ?? '?',
    painted: (button.children ?? []).some(paints),
    named: propOf(button, 'aria-label') !== undefined && propOf(button, 'title') !== undefined,
    slotted: icons.some((icon) => propOf(icon, 'slot') === 'icon-only'),
  };
}

/** Every `ion-button` of the template of `text` (the file `name`, a `.vue`) that holds an icon. */
export function iconButtons(text: string, name: string): IconButton[] {
  if (!name.endsWith('.vue') || !/<(?:ion-button|IonButton)\b/.test(text)) return [];
  const root = parse(text, { filename: name }).descriptor.template?.ast as unknown as TemplateNode | undefined;
  if (!root) return [];
  return [...elements(root)]
    .filter((node) => BUTTONS.has(node.tag ?? ''))
    .flatMap((button) => {
      const icons = [...elements(button)].filter((node) => ICONS.has(node.tag ?? ''));
      return icons.length > 0 ? [iconButton(button, icons)] : [];
    });
}

/** The lines of `text` (the file `file`) whose `ion-button` paints text beside its icon without being an exception. */
export function labelledButtons(text: string, file: string, exceptions = LABELLED_BUTTONS): number[] {
  const where = relative(HUB, file);
  return iconButtons(text, file)
    .filter((button) => button.painted && !(`${where}#${button.id}` in exceptions))
    .map((button) => button.line);
}

/** The lines of `text` (the file `file`) whose `ion-button` is only its icon but is not named or not squared. */
export function unnamedIconButtons(text: string, file: string, ownSquare = OWN_SQUARE): number[] {
  const where = relative(HUB, file);
  return iconButtons(text, file)
    .filter((button) => !button.painted && !(button.named && (button.slotted || `${where}#${button.id}` in ownSquare)))
    .map((button) => button.line);
}

describe('guardrail: an action button whose icon says it alone shows the icon alone', () => {
  const planted = [
    '<script setup lang="ts">',
    'const busy = false;',
    '</script>',
    '<template>',
    '  <div>',
    '    <ion-button data-testid="x-add"><HubIcon slot="start" icon="add-outline" />{{ $t(\'x.add\') }}</ion-button>',
    '    <ion-button :disabled="count > 1"><HubIcon slot="start" icon="add-outline" />Add</ion-button>',
    '    <ion-button :aria-label="$t(\'x.delete\')" :title="$t(\'x.delete\')">',
    '      <HubIcon slot="icon-only" icon="trash-outline" />',
    '    </ion-button>',
    '    <ion-button aria-label="Close"><HubIcon slot="icon-only" icon="close-outline" /></ion-button>',
    '    <ion-button :aria-label="label" :title="label"><HubIcon icon="close-outline" /></ion-button>',
    '    <ion-button data-testid="x-save">{{ $t(\'x.save\') }}</ion-button>',
    '    <ion-button data-testid="x-pay"><HubIcon slot="start" icon="card-outline" /><span>{{ amount }}</span></ion-button>',
    '    <ion-button><ion-spinner v-if="busy" /><HubIcon v-else slot="start" icon="send-outline" />{{ t(\'x.send\') }}</ion-button>',
    '  </div>',
    '</template>',
  ].join('\n');
  const file = join(HUB, 'apps', 'demo', 'frontend', 'Planted.vue');

  it('finds every button that paints text beside its icon, and lets the exceptions be', () => {
    expect(labelledButtons(planted, file, { 'apps/demo/frontend/Planted.vue#x-pay': 'planted' })).toEqual([6, 7, 15]);
    expect(iconButtons(planted, file).map(({ id }) => id)).toEqual(['x-add', '?', 'x.delete', '?', '?', 'x-pay', 'x.send']);
    expect(labelledButtons(planted, file.replace('.vue', '.ts'))).toEqual([]);
  });

  it('finds every button that is only its icon without its name, its title or the icon-only slot', () => {
    expect(unnamedIconButtons(planted, file)).toEqual([11, 12]);
    expect(unnamedIconButtons(planted.replace(':aria-label="label"', 'data-testid="x-close" :aria-label="label"'), file, {
      'apps/demo/frontend/Planted.vue#x-close': 'planted',
    })).toEqual([11]);
  });

  it('no button of base or of an app paints text beside its icon unless it is an exception', async () => {
    expect(await findingsByApp(hubFrontends({ ui: false }), labelledButtons), ICON_ALONE).toEqual({});
  }, NO_CLOCK);

  it('every button of base or of an app that is only its icon is named and squared', async () => {
    expect(await findingsByApp(hubFrontends({ ui: false }), unnamedIconButtons), NAMED_SQUARE).toEqual({});
  }, NO_CLOCK);

  it('a button that is only its icon is at least 36 px square with a mouse, and 44 px on a touch screen or a phone', () => {
    const css = readFileSync(join(HUB, 'frontend', 'icon-buttons.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
    const square = (size: number) => `ion-button\\.button-has-icon-only {\\s*min-width: ${size}px;\\s*min-height: ${size}px;\\s*}`;
    expect(css).toMatch(new RegExp(`^\\s*${square(36)}`));
    expect(css).toMatch(new RegExp(`@media \\(pointer: coarse\\), \\(max-width: 640px\\) {\\s*${square(44)}\\s*}`));
    expect(readFileSync(join(HUB, 'frontend', 'main.ts'), 'utf8')).toMatch(/^import '\.\/icon-buttons\.css';$/m);
  });

  it('every exception is still there: the lists only shrink', () => {
    const buttonsOf = (entry: string) => {
      const [path, id] = entry.split('#');
      return iconButtons(readFileSync(join(HUB, path), 'utf8'), path).filter((button) => button.id === id);
    };
    const labelled = Object.keys(LABELLED_BUTTONS).filter((entry) => !buttonsOf(entry).some((button) => button.painted));
    const squared = Object.keys(OWN_SQUARE).filter((entry) => !buttonsOf(entry).some((button) => !button.painted && !button.slotted));
    expect(labelled, 'strike the exceptions that no longer paint text beside their icon off LABELLED_BUTTONS').toEqual([]);
    expect(squared, 'strike the buttons that now sit in slot="icon-only" off OWN_SQUARE').toEqual([]);
  });
});
