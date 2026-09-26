// The name this shell TAB gives itself for the life of the page (hub#1980).
//
// Every open shell hears every `sale.completed` — the hub broadcasts one channel to all of them —
// and until this existed none could tell the sale it charged from the one the till next door
// charged: with two tills and a printer each, the ticket came out at both, as two originals.
// The shell sends this id as `X-Client-Instance` on its calls; the hub repeats it on the live frames
// those calls produce (`client_instance`), and the till acts only on its own.
//
// Per TAB, not per device, on purpose: two tabs of the same till are two listeners too, and only
// the one that charged should print. It names, it grants nothing — the hub treats it as a label.
// The hub accepts `[A-Za-z0-9_-]{1,64}` and DROPS anything else, so the shape is kept here.

function newInstanceId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  // `randomUUID` needs a secure context; a hub served over plain http on the LAN is not one.
  const bytes = new Uint8Array(16);
  c.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export const CLIENT_INSTANCE: string = newInstanceId();
