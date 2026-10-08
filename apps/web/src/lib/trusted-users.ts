// The faces this browser remembers for the PIN grid of Acceso (`erplora.trusted_users`).
//
// The hub is the authority on who may sign in with a PIN (`GET /api/hub/context` → `pin_users`);
// this list only decorates those people with their initials and keeps a face for a till that
// answers before the hub does. It holds what a face needs to be picked — id, name, initials — and
// never an e-mail (hub#2536): on a shared till it would hand the team's addresses to whoever walks
// up, and it outlives signing out, removing the device and switching it to «personal». The e-mail
// of whoever signs in comes from the hub's profile (`/api/profile`).

const KEY = 'erplora.trusted_users';

export interface TrustedUser {
  id: string;
  name: string;
  initials: string;
}

/** Only the fields a face needs, whatever else an older version stored next to them. */
function toFace(raw: unknown): TrustedUser | null {
  if (!raw || typeof raw !== 'object') return null;
  const { id, name, initials } = raw as Record<string, unknown>;
  if (typeof id !== 'string' || typeof name !== 'string') return null;
  return { id, name, initials: typeof initials === 'string' ? initials : '' };
}

/** `null` when the stored value is missing or is not a list of faces. */
function readStored(): TrustedUser[] | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.map(toFace).filter((u): u is TrustedUser => u !== null);
  } catch {
    return null;
  }
}

export function readTrustedUsers(): TrustedUser[] {
  return readStored() ?? [];
}

export function saveTrustedUsers(list: TrustedUser[]): void {
  const faces = list.map(toFace).filter((u): u is TrustedUser => u !== null);
  try {
    localStorage.setItem(KEY, JSON.stringify(faces));
  } catch {
    // A browser that does not store data (private window) simply has no remembered faces.
  }
}

/**
 * Called once at boot: rewrites what an older version stored without its e-mails, and drops a value
 * that is not a list of faces rather than keep whatever it holds. Nothing stored, nothing written.
 */
export function forgetTrustedUserEmails(): void {
  const faces = readStored();
  if (faces === null) {
    try {
      localStorage.removeItem(KEY);
    } catch {
      // Nothing more can be done in a browser that refuses storage.
    }
    return;
  }
  saveTrustedUsers(faces);
}
