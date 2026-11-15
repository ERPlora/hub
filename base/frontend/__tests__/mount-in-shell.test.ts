/* eslint-disable vue/one-component-per-file -- small screens built for these tests */
import { type SessionMe, type ShellConfig, useSession, useShellConfig } from '@erplora/ui/shell';
import { type ApiError, useLive, useLiveClient } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { defineComponent, h, inject, ref } from 'vue';
import { createMemoryHistory, createRouter, useRoute } from 'vue-router';

import { useBaseI18n } from '../lib/i18n';
import baseEs from '../locale/es.json';
import { business, POLISH } from './business';
import {
  click,
  ionChecked,
  ionValue,
  memoryRouter,
  mountInShell,
  overBase,
  page,
  settle,
  type ShellApp,
  subId,
  words,
} from './mount-in-shell';

const ANA: SessionMe = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'en' };
const LEO: SessionMe = { ...ANA, user: { id: 'u2', label: 'Leo' } };

const APP: ShellApp = {
  path: '/probe/home',
  session: ANA,
  messages: { en: { probe: { hello: 'Hello' } }, es: { probe: { hello: 'Hola' } } },
};

/** Says who is signed in, how the session stands, where the router is and a word of the app's catalogue. */
const Probe = defineComponent({
  props: { note: { type: String, default: '' } },
  setup(props) {
    const session = useSession();
    const route = useRoute();
    const { t } = useBaseI18n();
    return () =>
      h('div', [
        h('span', { 'data-testid': 'who' }, session.user.value?.label ?? 'nobody'),
        h('span', { 'data-testid': 'status' }, session.status.value),
        h('span', { 'data-testid': 'where' }, route.path),
        h('span', { 'data-testid': 'auth' }, String(route.meta.auth ?? false)),
        h('span', { 'data-testid': 'hello' }, t('probe.hello')),
        h('span', { 'data-testid': 'note' }, props.note),
      ]);
  },
});

/** Follows the demo items matching `search` and shows their total. */
const ItemTotal = defineComponent({
  name: 'ItemTotal',
  props: { search: { type: String, required: true } },
  setup(props) {
    const items = useLive('demo.item.list', () => ({ search: props.search }));
    return () => h('span', { 'data-testid': `total-${props.search}` }, String(items.data.value?.total ?? '-'));
  },
});

const TwoLists = defineComponent({ setup: () => () => h('div', [h(ItemTotal, { search: 'a' }), h(ItemTotal, { search: 'b' })]) });

/** Follows the business and shows its currency. */
const Money = defineComponent({
  setup() {
    const business = useLive('base.business.get', {});
    return () => h('span', { 'data-testid': 'currency' }, business.data.value?.currency ?? '-');
  },
});

/** Asks the API for the items matching «x» as it mounts and shows the total, or the refusal's code. */
const AsksOnMount = defineComponent({
  setup() {
    const said = ref('waiting');
    useLiveClient()
      .api.call('demo.item.list', { search: 'x' })
      .then(
        (answer) => (said.value = String(answer.total)),
        (error: ApiError) => (said.value = error.code),
      );
    return () => h('span', { 'data-testid': 'said' }, said.value);
  },
});

const Blank = defineComponent({ setup: () => () => h('div') });

describe('mountInShell: the app as the shell mounts it', () => {
  it("opens where the app's tests start, as its person, in its words, with the props the test gives", async () => {
    const m = await mountInShell(Probe, { props: { note: 'hi' } }, APP);

    expect(m.find('who').text()).toBe('Ana');
    expect(m.find('status').text()).toBe('live');
    expect(m.find('where').text()).toBe('/probe/home');
    expect(m.router.currentRoute.value.path).toBe('/probe/home');
    expect(m.find('hello').text()).toBe('Hello');
    expect(m.find('note').text()).toBe('hi');
  });

  it('takes the path, the person and the language the test names over the app\'s', async () => {
    const m = await mountInShell(Probe, { path: '/probe/other', session: LEO, locale: 'es' }, APP);

    expect(m.find('where').text()).toBe('/probe/other');
    expect(m.find('who').text()).toBe('Leo');
    expect(m.find('hello').text()).toBe('Hola');
  });

  it('mounts without a session when the test says `null`, in the status it names', async () => {
    const m = await mountInShell(Probe, { session: null, status: 'loading' }, APP);

    expect(m.find('who').text()).toBe('nobody');
    expect(m.find('status').text()).toBe('loading');
  });

  it('follows a session the test changes while the page is open', async () => {
    const session = ref(ANA);
    const m = await mountInShell(Probe, { session }, APP);

    session.value = LEO;
    await settle();

    expect(m.find('who').text()).toBe('Leo');
  });

  it('switches the language as the shell\'s selector does', async () => {
    const m = await mountInShell(Probe, {}, APP);

    await m.setLocale('es');

    expect(m.find('hello').text()).toBe('Hola');
  });

  it('attaches to the element the test names, and replaces the children it stubs', async () => {
    const Parent = defineComponent({ setup: () => () => h('div', [h(ItemTotal, { search: 'a' })]) });
    const Stubbed = defineComponent({ setup: () => () => h('p', { 'data-testid': 'stubbed' }) });

    const m = await mountInShell(Parent, { attachTo: document.body, stubs: { ItemTotal: Stubbed } }, APP);

    expect(document.body.contains(m.wrapper.element)).toBe(true);
    expect(m.find('stubbed').exists()).toBe(true);
    expect(m.client.stream.subscriptions('demo.item.list')).toHaveLength(0);
  });

  it("uses the app's router, the shell's config as createShell provides it and what else the app provides", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:path(.*)*', name: 'anywhere', component: Blank }],
    });
    const seen: { config?: ShellConfig; extra?: unknown } = {};
    const Reads = defineComponent({
      setup() {
        seen.config = useShellConfig();
        seen.extra = inject('extra');
        return () => h('div');
      },
    });

    const m = await mountInShell(
      Reads,
      {},
      { ...APP, router, shell: { homePath: '/start', home: true, sidebar: undefined }, provide: { extra: 'yes' } },
    );

    expect(m.router).toBe(router);
    expect(router.currentRoute.value.name).toBe('anywhere');
    expect(seen.config).toEqual({ homePath: '/start', home: true });
    expect(Object.isFrozen(seen.config)).toBe(true);
    expect(seen.extra).toBe('yes');
  });

  it('opens every path on a blank page with the meta the test gives (`memoryRouter`)', async () => {
    const m = await mountInShell(Probe, {}, { ...APP, router: memoryRouter({ auth: true }) });

    expect(m.find('where').text()).toBe('/probe/home');
    expect(m.find('auth').text()).toBe('true');
  });
});

describe('mountInShell: the stream', () => {
  it('pushes a result to the subscription whose params hold `match`, on the newest stream', async () => {
    const m = await mountInShell(TwoLists, {}, APP);
    await m.live();

    await m.result('demo.item.list', page([], 7), { search: 'b' });

    expect(m.find('total-a').text()).toBe('-');
    expect(m.find('total-b').text()).toBe('7');
    expect(m.params('demo.item.list')).toEqual([{ search: 'a' }, { search: 'b' }]);
    expect(m.subId('demo.item.list', { search: 'b' })).toBe(m.client.stream.subscriptions('demo.item.list')[1]!.id);
    expect(() => m.subId('demo.item.list', { search: 'c' })).toThrow('no live subscription for demo.item.list with {"search":"c"}');
  });

  it('pushes a result on the call the test holds: the first subscription, or the one with exactly `params`', async () => {
    const m = await mountInShell(TwoLists, {}, APP);
    const call = await m.live();

    await m.resultOn(call, 'demo.item.list', page([], 3));
    await m.resultOn(call, 'demo.item.list', page([], 9), 1, { search: 'b' });

    expect(m.find('total-a').text()).toBe('3');
    expect(m.find('total-b').text()).toBe('9');
  });

  it('names the subscription of an op: the first, the one with exactly those params, or none', async () => {
    const m = await mountInShell(TwoLists, {}, APP);
    const [first, second] = m.client.stream.subscriptions('demo.item.list');

    expect(subId(m.client, 'demo.item.list')).toBe(first!.id);
    expect(subId(m.client, 'demo.item.list', { search: 'b' })).toBe(second!.id);
    expect(() => subId(m.client, 'demo.item.list', { search: 'c' })).toThrow('no live subscription for demo.item.list');
    expect(() => subId(m.client, 'base.business.get')).toThrow('no live subscription for base.business.get');
  });

  it('reopens the stream the 150 ms the SDK waits after the subscriptions change', async () => {
    const m = await mountInShell(Blank, {}, APP);
    const before = m.clock.now();

    await m.reopen();

    expect(m.clock.now() - before).toBe(150);
  });

  it("answers the business as the stream opens when the app's pages follow it: the app's, the test's or never", async () => {
    const app: ShellApp = { ...APP, business: business({ currency: 'CHF' }) };

    const apps = await mountInShell(Money, {}, app);
    await apps.live();
    const tests = await mountInShell(Money, { business: business(POLISH) }, app);
    await tests.live();
    const never = await mountInShell(Money, { business: null }, app);
    await never.live();

    expect(apps.find('currency').text()).toBe('CHF');
    expect(tests.find('currency').text()).toBe('PLN');
    expect(never.find('currency').text()).toBe('-');
  });

  it('leaves the business unanswered for an app without one, or when no piece follows it', async () => {
    const quiet = await mountInShell(Money, {}, APP);
    await quiet.live();
    const nobody = await mountInShell(TwoLists, {}, { ...APP, business: business() });

    await expect(nobody.live()).resolves.toBeDefined();
    expect(quiet.find('currency').text()).toBe('-');
    expect(nobody.find('total-a').text()).toBe('-');
  });
});

describe('mountInShell: the API', () => {
  it('answers what a component asks as it mounts with the handler the test gives', async () => {
    const m = await mountInShell(AsksOnMount, { api: () => Response.json(page([], 4)) }, APP);
    await settle();

    expect(m.find('said').text()).toBe('4');
  });

  it('answers by path from before the mount, a held reply when the test sends it, and a 404 envelope otherwise', async () => {
    const listed = await mountInShell(AsksOnMount, { answers: { '/api/demo/items': [200, page([], 5)] } }, APP);
    let release!: () => void;
    const held = await mountInShell(
      AsksOnMount,
      { answers: { '/api/demo/items': () => new Promise((done) => (release = () => done(Response.json(page([], 6))))) } },
      APP,
    );
    const unlisted = await mountInShell(AsksOnMount, { answers: { '/api/elsewhere': [200, {}] } }, APP);
    await settle();

    expect(listed.find('said').text()).toBe('5');
    expect(held.find('said').text()).toBe('waiting');
    expect(unlisted.find('said').text()).toBe('not_found');
    release();
    await settle();
    expect(held.find('said').text()).toBe('6');
  });

  it('answers every later call alike (`answer`) or by path (`answerBy`)', async () => {
    const m = await mountInShell(Blank, {}, APP);

    m.answer(409, { error: { code: 'demo.taken', message: 'Taken' } });
    const refused = await m.client.api.call('demo.item.list', {}).catch((error: ApiError) => error.code);
    m.answerBy({ '/api/demo/items': [200, page([], 2)] });
    const listed = await m.client.api.call('demo.item.list', {});

    expect(refused).toBe('demo.taken');
    expect(listed.total).toBe(2);
  });

  it('reads back what the page sent: method, path, query and JSON body', async () => {
    const m = await mountInShell(Blank, { api: () => Response.json({}) }, APP);

    await m.client.api.call('demo.item.list', { search: 'tea' });
    await m.client.api.call('demo.item.create', { name: 'Tea' } as never);

    expect(m.sent()).toEqual([
      { method: 'GET', path: '/api/demo/items', query: { search: 'tea' }, body: undefined },
      { method: 'POST', path: '/api/demo/items', query: {}, body: { name: 'Tea' } },
    ]);
  });
});

describe('mountInShell: finding what the screen painted', () => {
  /** Two roots: the first holds a «twin» inside, the second is one itself. */
  const TwoRoots = defineComponent({
    setup: () => () => [h('div', [h('i', { 'data-testid': 'twin', id: 'inside' })]), h('b', { 'data-testid': 'twin', id: 'root' })],
  });

  /** Something on the body, outside the mount (a dialog's own host). */
  let away: HTMLElement;
  beforeEach(() => {
    away = Object.assign(document.createElement('p'), { id: 'away' });
    away.dataset.testid = 'away';
    document.body.append(away);
  });
  afterEach(() => away.remove());

  it("looks in the mount's container first, in the document's order, then in the document", async () => {
    const m = await mountInShell(TwoRoots, {}, APP);

    expect(m.inDoc('twin')?.id).toBe('inside');
    expect(m.inDoc('away')?.id).toBe('away');
    expect(m.find('away').exists()).toBe(false);
    expect(m.inDoc('missing')).toBeNull();
  });

  it("looks in the component's own nodes first when the app says so, its roots before what they hold", async () => {
    const m = await mountInShell(TwoRoots, {}, { ...APP, inDocFrom: 'component' });

    expect(m.inDoc('twin')?.id).toBe('root');
    expect(m.inDoc('away')?.id).toBe('away');
    expect(m.inDoc('missing')).toBeNull();
  });
});

describe('the gestures and fixtures the tests share', () => {
  it('sets a value as Ionic does and lets what it set off render', async () => {
    const input = document.createElement('div');
    const seen: unknown[] = [];
    input.addEventListener('ionInput', (event) => seen.push((event as CustomEvent).detail.value));

    await ionValue(input, 'Tea', 'ionInput');

    expect((input as HTMLElement & { value?: unknown }).value).toBe('Tea');
    expect(seen).toEqual(['Tea']);
    await expect(ionValue(null, 'x')).rejects.toThrow('no element to set');
  });

  it('checks a toggle as Ionic does', async () => {
    const toggle = document.createElement('div');
    const seen: unknown[] = [];
    toggle.addEventListener('ionChange', (event) => seen.push((event as CustomEvent).detail));

    await ionChecked(toggle, true);

    expect((toggle as HTMLElement & { checked?: boolean }).checked).toBe(true);
    expect(seen).toEqual([{ checked: true, value: 'on' }]);
    await expect(ionChecked(null, true)).rejects.toThrow('no element to toggle');
  });

  it('clicks as a person does: one bubbling click', async () => {
    const button = document.createElement('button');
    const parent = document.createElement('div');
    parent.append(button);
    let clicks = 0;
    parent.addEventListener('click', () => clicks++);

    await click(button);

    expect(clicks).toBe(1);
    await expect(click(null)).rejects.toThrow('nothing to click');
  });

  it('reads the words a person reads, one space apart, no-break spaces as plain ones', () => {
    const box = document.createElement('div');
    box.innerHTML = '<b>12,50 €</b>  <i> 1 000 paid </i><span></span>';

    expect(words(box)).toBe('12,50 € 1 000 paid');
  });

  it("puts base's words under the app's, as the hub loads base's for every app", () => {
    const { en, es } = overBase({ base: { save: 'Keep' }, probe: { hello: 'Hello' } }, { probe: { hello: 'Hola' } });

    expect(en.probe).toEqual({ hello: 'Hello' });
    expect(en.base).toEqual({ save: 'Keep' });
    expect(es.probe).toEqual({ hello: 'Hola' });
    expect(es.base).toEqual(baseEs.base);
  });

  it('builds a page of a list as the server answers it', () => {
    expect(page(['a', 'b'])).toEqual({ rows: ['a', 'b'], total: 2, limit: 50, offset: 0 });
    expect(page(['a'], 9, 1, 3)).toEqual({ rows: ['a'], total: 9, limit: 1, offset: 3 });
  });
});
