// Loading, failed and empty are three different sentences, and a list must never say one meaning
// another (hub#770).
//
// «You have no apps yet» is a FACT about the hub. The panel and «Apps → My apps» were saying it
// whenever they simply did not know: for the ~3 seconds of a cold load, and — worse — after a failed
// request, because a `catch` that assigns `[]` turns «I could not ask» into «there is nothing». A
// person whose session had just been displaced by a second device was told their twelve installed
// apps were gone, on a screen whose only offer is «install your first one», while the till in the
// next tab was still selling.
//
// The rule below is one line long and it is the whole fix: DATA WINS. Rows already on screen stay on
// screen while the list reloads and after it fails; «empty» is only ever said about an answer that
// came back and said so.

/** What a list knows about its own last request. */
export type ListLoadState = 'loading' | 'ready' | 'error';

/** What the view must paint. */
export type ListDisplay = 'items' | 'loading' | 'error' | 'empty';

/**
 * Which of the four a list should show, given what it knows and what it already has.
 *
 * Order matters. Rows come first, before both the spinner and the failure: replacing what somebody
 * is reading with a spinner is a second lie, and the last known-good list beats every message we
 * could put in its place. The failure still has to reach the user — a banner, a retry — but next to
 * the data, not instead of it.
 */
export function listDisplay(state: ListLoadState, itemCount: number): ListDisplay {
  if (itemCount > 0) return 'items';
  if (state === 'loading') return 'loading';
  if (state === 'error') return 'error';
  return 'empty';
}
