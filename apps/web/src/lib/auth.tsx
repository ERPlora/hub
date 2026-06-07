// Capa de autenticación de hub (cliente). Modela el flujo real (ARQUITECTURA.md §2.9):
//   1) 1er login email+password (online) → marca dispositivo de confianza → PIN
//   2) dispositivo de confianza → login por PIN (local/offline a futuro)
//   3) usuarios cloud y usuarios solo-locales
//
// ESTADO: el runtime Rust (verify PIN local, SQLite) aún no existe. Hasta entonces, esta
// capa habla con el Cloud para email+password y, si el Cloud no es accesible (sandbox) o
// está en modo demo, degrada a un flujo DEMO local. Todo el estado de sesión/dispositivo
// vive en localStorage. La lógica de UI es idéntica el día que exista el runtime.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { config } from './config';
import { cloudLogin, setTokens, clearTokens, type CloudUser } from './cloud';

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  isAdmin: boolean;
  kind: 'cloud' | 'local';
  /** Foto de perfil (si el Cloud la expone algun dia). Hoy siempre null → iniciales. */
  avatarUrl?: string | null;
}

export interface TrustedDeviceUser {
  id: string;
  name: string;
  email: string;
  initials: string;
}

interface AuthState {
  user: SessionUser | null;
  ready: boolean;
  /** ¿Este dispositivo ya es de confianza? (habilita login por PIN) */
  trusted: boolean;
  /** Usuarios disponibles para login por PIN en este dispositivo. */
  trustedUsers: TrustedDeviceUser[];
}

interface AuthApi extends AuthState {
  loginEmail: (email: string, password: string, trustDevice: boolean) => Promise<{ firstTime: boolean }>;
  setupPin: (pin: string) => Promise<void>;
  loginPin: (userId: string, pin: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthApi | null>(null);

const LS = {
  session: 'erplora.session',
  device: 'erplora.device', // { trusted, users: [{id,name,email,initials,pinHash}] }
  pending: 'erplora.pending', // login email pendiente de setup de PIN
};

interface DeviceRecord {
  trusted: boolean;
  users: Array<TrustedDeviceUser & { pin: string }>; // pin en claro SOLO en demo local; con runtime → hash en Rust
}

function readDevice(): DeviceRecord {
  try {
    const raw = localStorage.getItem(LS.device);
    if (raw) return JSON.parse(raw) as DeviceRecord;
  } catch { /* ignore */ }
  return { trusted: false, users: [] };
}
function writeDevice(d: DeviceRecord) {
  localStorage.setItem(LS.device, JSON.stringify(d));
}
function initials(name: string): string {
  return name.split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || '?';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const [device, setDevice] = useState<DeviceRecord>({ trusted: false, users: [] });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS.session);
      if (raw) setUser(JSON.parse(raw) as SessionUser);
    } catch { /* ignore */ }
    setDevice(readDevice());
    setReady(true);
  }, []);

  const persist = useCallback((u: SessionUser | null) => {
    setUser(u);
    if (u) localStorage.setItem(LS.session, JSON.stringify(u));
    else localStorage.removeItem(LS.session);
  }, []);

  const loginEmail = useCallback<AuthApi['loginEmail']>(async (email, password, trustDevice) => {
    let cloudUser: CloudUser | null = null;
    try {
      const res = await cloudLogin(email, password);
      cloudUser = res.user;
      // Persistimos el JWT para las llamadas autenticadas (billing, etc.).
      setTokens(res.access, res.refresh);
    } catch (err) {
      // Cloud no accesible o credenciales inválidas. En demo, aceptamos y simulamos.
      if (!config.demo) throw err;
      cloudUser = { id: `demo-${email}`, name: email.split('@')[0], email };
    }
    // Guardamos el login como "pendiente de PIN" (primer setup) si el dispositivo no tiene
    // todavía este usuario; si ya existe, entramos directamente.
    const dev = readDevice();
    const existing = dev.users.find((u) => u.email === cloudUser!.email);
    if (existing) {
      // Re-sincroniza la foto desde el /me/ fresco en cada login (no solo el 1er setup).
      persist({ id: existing.id, name: existing.name, email: existing.email, isAdmin: true, kind: 'cloud', avatarUrl: cloudUser.avatarUrl ?? null });
      return { firstTime: false };
    }
    localStorage.setItem(LS.pending, JSON.stringify({ ...cloudUser, trustDevice }));
    return { firstTime: true };
  }, [persist]);

  const setupPin = useCallback<AuthApi['setupPin']>(async (pin) => {
    const raw = localStorage.getItem(LS.pending);
    if (!raw) throw new Error('No hay login pendiente');
    const pending = JSON.parse(raw) as CloudUser & { trustDevice: boolean };
    const dev = readDevice();
    const rec: TrustedDeviceUser & { pin: string } = {
      id: pending.id,
      name: pending.name,
      email: pending.email,
      initials: initials(pending.name),
      pin, // DEMO: en claro. Con runtime Rust → hash bcrypt local.
    };
    dev.users = [...dev.users.filter((u) => u.email !== pending.email), rec];
    if (pending.trustDevice) dev.trusted = true;
    writeDevice(dev);
    setDevice(dev);
    localStorage.removeItem(LS.pending);
    persist({ id: pending.id, name: pending.name, email: pending.email, isAdmin: true, kind: 'cloud', avatarUrl: pending.avatarUrl ?? null });
  }, [persist]);

  const loginPin = useCallback<AuthApi['loginPin']>(async (userId, pin) => {
    const dev = readDevice();
    const u = dev.users.find((x) => x.id === userId);
    if (!u) throw new Error('Usuario no encontrado en este dispositivo');
    if (u.pin !== pin) throw new Error('PIN incorrecto');
    persist({ id: u.id, name: u.name, email: u.email, isAdmin: true, kind: 'cloud' });
  }, [persist]);

  const logout = useCallback(() => {
    persist(null);
    clearTokens();
  }, [persist]);

  const value = useMemo<AuthApi>(() => ({
    user,
    ready,
    trusted: device.trusted && device.users.length > 0,
    trustedUsers: device.users.map(({ id, name, email, initials: ini }) => ({ id, name, email, initials: ini })),
    loginEmail,
    setupPin,
    loginPin,
    logout,
  }), [user, ready, device, loginEmail, setupPin, loginPin, logout]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth fuera de AuthProvider');
  return ctx;
}
