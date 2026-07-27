import { runtimeCourierSession, setTokens } from './cloud';
import { getDeviceContext } from './device';
import { setHubSession, setUser } from './session';

const COURIER_KEY = 'courier';

/**
 * Take the opaque courier credential out of the URL fragment and scrub it synchronously.
 * Fragments are not sent to HTTP servers or in Referer headers; replacing history here also keeps
 * the one-time code out of screenshots, copy/paste and later browser history entries.
 */
export function takeCourierCode(
  locationLike: Pick<Location, 'hash' | 'pathname' | 'search'> = window.location,
  replace: (url: string) => void = (url) => window.history.replaceState(null, '', url),
): string | null {
  if (!locationLike.hash.startsWith('#')) return null;
  const params = new URLSearchParams(locationLike.hash.slice(1));
  const code = params.get(COURIER_KEY)?.trim() ?? '';
  if (!code) return null;
  replace(`${locationLike.pathname}${locationLike.search}`);
  return code.length <= 128 ? code : null;
}

/** Complete shell auto-login before Vue/router mount.  Only the local opaque session and the same
 * Cloud tokens used by the ordinary login flow are persisted; no credential is logged. */
export async function bootCourier(code: string | null = takeCourierCode()): Promise<boolean> {
  if (!code) return false;

  const device = await getDeviceContext();
  const result = await runtimeCourierSession(code, device?.id);
  setTokens(result.access, result.refresh);
  setHubSession(result.token);
  setUser({
    id: result.user.id,
    cloudUserId: result.cloud_user.id,
    name: result.cloud_user.name,
    email: result.cloud_user.email,
    role: result.user.role,
    permissions: result.permissions,
  });
  return true;
}
