// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { runtimeCourierSession, setTokens, setHubSession, setUser } = vi.hoisted(() => ({
  runtimeCourierSession: vi.fn(),
  setTokens: vi.fn(),
  setHubSession: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock('./cloud', () => ({ runtimeCourierSession, setTokens }));
vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
}));
vi.mock('./session', () => ({ setHubSession, setUser }));

import { bootCourier, takeCourierCode } from './courier';

describe('shell courier boot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, '', '/?shell=1');
  });

  it('extracts the fragment and scrubs it before any exchange', () => {
    const replace = vi.fn();
    const code = takeCourierCode(
      { hash: '#courier=opaque-code', pathname: '/', search: '?shell=1' },
      replace,
    );
    expect(code).toBe('opaque-code');
    expect(replace).toHaveBeenCalledWith('/?shell=1');
  });

  it('opens and stores the same local/cloud session shape as normal login', async () => {
    window.history.replaceState(null, '', '/?shell=1#courier=opaque-code');
    runtimeCourierSession.mockResolvedValue({
      access: 'access-jwt',
      refresh: 'refresh-jwt',
      token: 'local-session',
      user: { id: 'local-1', name: 'Ana', role: 'employee' },
      permissions: ['sales.read'],
      cloud_user: { id: 'cloud-1', name: 'Ana', email: 'ana@example.com' },
    });

    await expect(bootCourier()).resolves.toBe(true);
    expect(window.location.hash).toBe('');
    expect(runtimeCourierSession).toHaveBeenCalledWith('opaque-code', 'device-1');
    expect(setTokens).toHaveBeenCalledWith('access-jwt', 'refresh-jwt');
    expect(setHubSession).toHaveBeenCalledWith('local-session');
    expect(setUser).toHaveBeenCalledWith(expect.objectContaining({
      id: 'local-1', cloudUserId: 'cloud-1', role: 'employee',
    }));
  });
});
