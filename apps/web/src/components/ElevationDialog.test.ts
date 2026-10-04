// @vitest-environment happy-dom
// hub#363 (4/4) — **the dialog**. The last piece of the chain that was already whole underneath:
// the runtime tells a cashier «a manager could approve this» (hub#360), verifies the manager's PIN
// and mints a one-action approval (hub#361) and writes the receipt of every approval spent
// (hub#362). Until this screen existed, none of it could be reached from a till.
//
// What this suite pins is the behaviour that decides whether the whole design survives contact
// with a counter:
//
//   - the PIN goes to the RUNTIME and nowhere else — this screen never decides whether four digits
//     are right, and never learns it except through the answer;
//   - a refused PIN keeps the dialog open, because the alternative is fetching the manager twice;
//   - closing it is a legitimate answer, and it hands the caller back the refusal it already had;
//   - and, above all, the caller waits: the promise is resolved exactly once, by a person.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { ErploraError, HttpWsTransport, type ElevationAsk } from '@erplora/module-sdk';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return { pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]) };
});
const toast = vi.fn();
vi.mock('../lib/toast', () => ({ toast: (...args: unknown[]) => toast(...args) }));

import ElevationDialog from './ElevationDialog.vue';
import { pinUsers } from '../lib/runtime';
import { askForApproval, pendingElevation, resolveElevation } from '../lib/elevation';
import { installBadgeScanner, onBadgeScan } from '../lib/badge-scanner';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** Todo lo montado por el test en curso, para desmontarlo al terminar.
 *
 * No es higiene decorativa: este componente se **suscribe al lector de placas** mientras hay algo
 * que aprobar (hub#658), y un diálogo que sobrevive a su test sigue vivo y sigue suscribiéndose en
 * los siguientes. La ráfaga la recibe el ÚLTIMO suscrito, así que un montaje huérfano se queda con
 * la tarjeta del test de al lado — y el fallo aparece a varios tests de distancia de su causa. */
const mounted: Array<{ unmount: () => void }> = [];

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount();
});

function mountDialog() {
  // shallow: the `ion-*` are stubbed (this is the dialog's contract, not Ionic's), but the slot is
  // still rendered — a real `ion-modal` reparents its content to <body> and there would be nothing
  // to look at. The `ok-*` are custom ELEMENTS, so they survive shallow and can be fired at.
  const wrapper = mount(ElevationDialog, {
    shallow: true,
    global: {
      plugins: [i18n],
      renderStubDefaultSlot: true,
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  mounted.push(wrapper);
  return wrapper;
}

/** `is-open` of the modal, read as a prop: on a stub, a `false` boolean leaves no attribute. */
const modal = (w: ReturnType<typeof mountDialog>): VueWrapper =>
  w.getComponent('[data-testid="elevation-modal"]') as VueWrapper;
const isOpen = (w: ReturnType<typeof mountDialog>): unknown =>
  (modal(w).props() as Record<string, unknown>).isOpen;

/** An ask whose `approve` is scripted, so the test can be the runtime's answer. */
function ask(
  approve: ElevationAsk['approve'],
  approveWithBadge: ElevationAsk['approveWithBadge'] = async () => {
    throw new Error('this ask was not scripted for a badge');
  },
): ElevationAsk {
  return {
    command: 'till.sale.void',
    payload: { sale_id: 's1' },
    permission: 'till.void_sale',
    approve,
    approveWithBadge,
  };
}

const approves = vi.fn(async () => ({
  token: 'tok-abc',
  permission: 'till.void_sale',
  approvedBy: 'u-sofia',
  approverName: 'Sofía',
  expiresInSeconds: 120,
}));

/** The counter till: two people the hub knows can sign in locally. */
function seedPeople(): void {
  pinUsers.value = [
    { id: 'u1', name: 'Nacho', role: 'employee' },
    { id: 'u2', name: 'Sofía', role: 'manager' },
  ];
}

/** Tap the person, then type four digits on the pinpad. */
async function approveAs(w: ReturnType<typeof mountDialog>, name: string, pin: string): Promise<void> {
  const card = w.findAll('[data-testid="elevation-person"]').find((c) => c.text().includes(name));
  await card!.trigger('click');
  w.find('[data-testid="elevation-pinpad"]').element.dispatchEvent(
    new CustomEvent('ok-complete', { detail: { value: pin } }),
  );
  await flushPromises();
}

beforeEach(() => {
  resolveElevation(null);
  pinUsers.value = [];
  approves.mockClear();
  toast.mockClear();
  i18n.global.locale.value = 'en';
});

describe('what the cashier is shown', () => {
  it('says nothing at all while nobody is asking', () => {
    const w = mountDialog();
    expect(isOpen(w)).toBe(false);
  });

  it('asks for the gesture, not for an explanation', async () => {
    seedPeople();
    void askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();

    expect(isOpen(w)).toBe(true);
    expect(w.find('[data-testid="elevation-lead"]').text()).toBe(en.elevation.lead);
    // The permission the refusal named (`till.void_sale`) is our vocabulary, not the counter's: it
    // is what the transport re-sends and what the runtime re-checks, and it must not be printed at
    // somebody who is holding up a queue.
    expect(w.text()).not.toContain('till.void_sale');
    expect(w.text()).not.toContain('till.sale.void');
  });

  it('offers the people the hub knows, so approving is a tap and not a spelling test', async () => {
    seedPeople();
    void askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();

    const names = w.findAll('[data-testid="elevation-person"]').map((c) => c.text());
    expect(names.some((n) => n.includes('Sofía'))).toBe(true);
    // Not filtered by role, on purpose: who may approve is the runtime's answer, and a list
    // narrowed to managers would publish who they are to whoever opens the dialog.
    expect(names.some((n) => n.includes('Nacho'))).toBe(true);
  });

  it('falls back to typing a name when the hub named nobody', async () => {
    void askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();
    expect(w.findAll('[data-testid="elevation-person"]')).toHaveLength(0);
    expect(w.find('[data-testid="elevation-name"]').exists()).toBe(true);
  });

  it('will not go on with an empty name', async () => {
    // An empty approver is not a nameless request, it is a request against the name `''` — and
    // every refusal of it counts towards the brute-force guard keyed on exactly that name. One
    // impatient tap on «Continue» and the till is throttling a person who does not exist.
    void askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();
    const props = (w.getComponent('[data-testid="elevation-continue"]') as VueWrapper).props();
    expect((props as Record<string, unknown>).disabled).toBe(true);
  });
});

describe('the PIN', () => {
  it('is verified by the runtime — this screen only carries it', async () => {
    seedPeople();
    const pending = askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '8317');

    // Through the ask, which is the transport's door to `POST /api/elevation/approve`. The screen
    // holds no endpoint, no header and no opinion about whether 8317 is right.
    expect(approves).toHaveBeenCalledWith('Sofía', '8317');
    expect(await pending).toBe('tok-abc');
    expect(pendingElevation.value).toBeNull();
  });

  it('tells the cashier who allowed it', async () => {
    // The confirmation the approval exists to produce. The action is now recorded under two names,
    // and saying the second one out loud is half of what keeps the trail honest.
    seedPeople();
    void askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '8317');

    expect(toast).toHaveBeenCalled();
    expect(String(toast.mock.calls[0][0])).toContain('Sofía');
  });

  it('keeps the dialog open when the runtime refuses it, and says so in one sentence', async () => {
    // The manager mistyped. Closing here would send them back to the till for a typo — and a shop
    // that finds approving painful shares one credential instead, which is the failure this whole
    // chain exists to prevent.
    seedPeople();
    const refuses = vi.fn(async () => {
      throw new ErploraError('hub.elevation.rejected', 'those details do not approve this action.');
    });
    const pending = askForApproval(ask(refuses));
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '0000');

    expect(w.find('[data-testid="elevation-error"]').text()).toBe(en.elevation.rejected);
    expect(pendingElevation.value, 'still asking').not.toBeNull();

    let settled = false;
    void pending.then(() => {
      settled = true;
    });
    await flushPromises();
    expect(settled, 'the caller is still waiting, not refused').toBe(false);
  });

  it('says «wait», not «wrong PIN», when the brute-force guard closes the door', async () => {
    // Two guards, two sentences. Answering «check the PIN» to a manager whose PIN is right sends
    // them round the loop that earned the lock in the first place.
    seedPeople();
    const throttled = vi.fn(async () => {
      throw new ErploraError('too_many_attempts', 'too many failed attempts');
    });
    void askForApproval(ask(throttled));
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '0000');

    // hub#2285: a refusal that names no wait is the pinpad's own «wait a few minutes» — one
    // sentence for the one lock, at every door.
    expect(w.find('[data-testid="elevation-error"]').text()).toBe(en.login.pinTooManyAttemptsNoWait);
    expect(w.find('[data-testid="elevation-error"]').text()).not.toBe(en.elevation.rejected);
  });

  // hub#2285: the approval spends tries against the same lock as the login pinpad (per name, and
  // per address with hub#2282), so when the refusal carries the wait it says the same minutes.
  it.each([
    ['en', 240, 4],
    ['es', 240, 4],
    ['en', 20, 1],
    ['es', 20, 1],
  ] as const)('says how many minutes a lock lasts (%s, %is → %i)', async (locale, secs, minutes) => {
    i18n.global.locale.value = locale;
    const say = (n: number): string => i18n.global.t('login.pinTooManyAttempts', { minutes: n }, n);
    seedPeople();
    const throttled = vi.fn(async () => {
      throw new ErploraError('too_many_attempts', 'too many failed attempts', undefined, undefined, secs);
    });
    void askForApproval(ask(throttled));
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '0000');

    expect(w.find('[data-testid="elevation-error"]').text()).toBe(say(minutes));
    expect(say(1)).not.toBe(say(2).replace('2', '1'));
  });

  // hub#2290: the case above, but with the wait coming off the WIRE. The approval travels through
  // the SDK's transport, and that is where it was lost: the hub answered 429 with
  // `error.retry_after_secs` and the dialog still said «a few minutes». Wired as `runtime.ts` wires
  // it (`elevationApprover: askForApproval`), with only `fetch` scripted.
  it.each([
    ['en', 240, 4],
    ['es', 240, 4],
  ] as const)('says the minutes the hub named on the wire (%s, %is → %i)', async (locale, secs, minutes) => {
    i18n.global.locale.value = locale;
    seedPeople();
    const replies = [
      { ok: false, error: { code: 'requires_elevation', message: 'needs a manager', permission: 'till.void_sale' } },
      {
        ok: false,
        error: {
          code: 'too_many_attempts',
          message: 'too many failed attempts: wait a few minutes before approving again',
          retry_after_secs: secs,
        },
      },
    ];
    let n = 0;
    const fetchImpl = (async () => {
      const body = replies[n++];
      return { status: n === 2 ? 429 : 403, json: async () => body };
    }) as unknown as typeof fetch;
    const transport = new HttpWsTransport({ fetchImpl, elevationApprover: askForApproval });
    void transport.command('till.sale.void', { sale_id: 's1' }).catch(() => {});
    await flushPromises();
    const w = mountDialog();
    await flushPromises();
    await approveAs(w, 'Sofía', '0000');

    expect(n, 'the PIN went to the approval door').toBe(2);
    expect(w.find('[data-testid="elevation-error"]').text()).toBe(
      i18n.global.t('login.pinTooManyAttempts', { minutes }, minutes),
    );
    resolveElevation(null);
  });

  it('is never sent twice for one tap', async () => {
    // The pinpad fires `ok-complete` on the fourth digit, and a second one can arrive while the
    // first request is still in the air. Each attempt spends one of five tries against the
    // approver's name: two requests for one tap halve the manager's budget for a typo.
    seedPeople();
    type Approval = Awaited<ReturnType<ElevationAsk['approve']>>;
    let release: (v: Approval) => void = () => {};
    const slow = vi.fn(
      () =>
        new Promise<Approval>((resolve) => {
          release = resolve;
        }),
    );
    void askForApproval(ask(slow));
    const w = mountDialog();
    await flushPromises();

    const card = w.findAll('[data-testid="elevation-person"]').find((c) => c.text().includes('Sofía'));
    await card!.trigger('click');
    const pad = w.find('[data-testid="elevation-pinpad"]').element;
    pad.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '8317' } }));
    pad.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '8317' } }));
    await flushPromises();

    expect(slow).toHaveBeenCalledTimes(1);
    release({ token: 't', permission: 'p', approvedBy: 'u', approverName: 'Sofía', expiresInSeconds: 120 });
  });
});

describe('giving up is an answer', () => {
  it('hands the caller back the refusal it already had', async () => {
    seedPeople();
    const pending = askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();

    await w.find('[data-testid="elevation-cancel"]').trigger('click');
    expect(await pending).toBeNull();
    expect(approves, 'nothing was sent').not.toHaveBeenCalled();
    expect(pendingElevation.value).toBeNull();
  });

  it('treats a dismissal by backdrop exactly the same', async () => {
    seedPeople();
    const pending = askForApproval(ask(approves));
    const w = mountDialog();
    await flushPromises();

    modal(w).vm.$emit('didDismiss');
    expect(await pending).toBeNull();
  });
});

// ── hub#658 — the manager's CARD approves what the manager's PIN approves ────────────────────

describe('the badge', () => {
  /** A reader's burst: fast characters, a trailing Enter, and no field focused anywhere. */
  function swipe(badge: string): void {
    for (const ch of badge) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
    }
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  }

  const approvesBadge = vi.fn(async () => ({
    token: 'tok-badge',
    permission: 'till.void_sale',
    approvedBy: 'u-sofia',
    approverName: 'Sofía',
    expiresInSeconds: 120,
  }));

  let uninstall: () => void;
  beforeEach(() => {
    approvesBadge.mockClear();
    uninstall = installBadgeScanner();
  });
  // En `afterEach` y no al final de cada test: un test que falla a mitad dejaría el listener
  // puesto, y el siguiente vería CADA tecla dos veces — un fallo que no se parece en nada a su
  // causa (la ráfaga sale con los caracteres duplicados).
  afterEach(() => uninstall());

  it('approves without anybody being tapped on the grid first', async () => {
    // The market decision in one assertion (Toast, Aloha, Square): swiping the card IS the
    // approval. A badge resolves the whole person, so there is no name to choose and no pinpad to
    // reach — which is exactly the friction the sector removed twenty years ago.
    seedPeople();
    const pending = askForApproval(ask(approves, approvesBadge));
    mountDialog();
    await flushPromises();

    swipe('0009171456');
    await flushPromises();

    expect(approvesBadge).toHaveBeenCalledWith('0009171456');
    expect(approves).not.toHaveBeenCalled();
    expect(await pending).toBe('tok-badge');
    expect(pendingElevation.value).toBeNull();
  });

  it('keeps the dialog open when the card is refused, exactly as a wrong PIN does', async () => {
    seedPeople();
    const refuses = vi.fn(async () => {
      throw new ErploraError('hub.elevation.approver_cannot', 'that person cannot approve this');
    });
    void askForApproval(ask(approves, refuses));
    const w = mountDialog();
    await flushPromises();

    swipe('0009171456');
    await flushPromises();

    expect(w.find('[data-testid="elevation-error"]').text()).toBe(en.elevation.approverCannot);
    expect(pendingElevation.value, 'still asking').not.toBeNull();
  });

  it('wins over the screen underneath, and only while there is something to approve', async () => {
    // The employee form also listens (the reader fills its badge field). `onBadgeScan` delivers to
    // the LAST subscriber, so a dialog that subscribed on MOUNT would lose to a page mounted after
    // it — and a swipe meant to approve a void would enrol a card in a form instead.
    seedPeople();
    mountDialog();
    await flushPromises();

    const page: string[] = [];
    const offPage = onBadgeScan((badge) => page.push(badge));

    // Nothing to approve yet: the dialog is not listening, so the screen behind gets the card.
    swipe('0009171456');
    await flushPromises();
    expect(page).toEqual(['0009171456']);

    // An ask arrives → the dialog takes over.
    const pending = askForApproval(ask(approves, approvesBadge));
    await flushPromises();
    swipe('0009171456');
    await flushPromises();
    expect(page).toEqual(['0009171456']); // el diálogo se la quedó: la página no oyó nada
    expect(await pending).toBe('tok-badge');

    // …and hands the door back once it closes.
    await flushPromises();
    swipe('0009171456');
    await flushPromises();
    expect(page).toEqual(['0009171456', '0009171456']);

    offPage();
  });

  it('is offered in words, so nobody has to know the card works here', async () => {
    seedPeople();
    void askForApproval(ask(approves, approvesBadge));
    const w = mountDialog();
    await flushPromises();

    expect(w.find('[data-testid="elevation-badge-hint"]').text()).toBe(en.elevation.orSwipeBadge);
  });
});
