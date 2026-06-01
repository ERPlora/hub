// Chrome de la app: sidebar (desktop) · topbar glass · drawer (móvil) · tabbar contextual.
// Portado del prototipo a TS + props tipadas. ARQUITECTURA.md §7.7.
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from './Icon';
import { Logo } from './Logo';

export interface NavItem {
  id: string;
  label: string;
  icon: string;
}
export interface NavSection {
  label: string;
  items: NavItem[];
}
export interface TabItem {
  id: string;
  label: string;
  icon: string;
}

export interface ShellUser {
  name: string;
  email: string;
  initials: string;
}

export interface AppShellProps {
  title: string;
  subtitle?: string;
  nav: NavSection[];
  activeNavId: string;
  onNav: (id: string) => void;
  workspace?: string;
  onWorkspace?: (w: string) => void;
  workspaces?: string[];
  tabs?: { items: TabItem[]; active: string; onChange: (id: string) => void };
  dark: boolean;
  onToggleDark: () => void;
  user: ShellUser;
  onLogout?: () => void;
  notif?: number;
  pageActions?: ReactNode;
  children: ReactNode;
}

function useMedia(query: string): boolean {
  const [match, setMatch] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false));
  useEffect(() => {
    const m = window.matchMedia(query);
    const h = () => setMatch(m.matches);
    m.addEventListener('change', h);
    return () => m.removeEventListener('change', h);
  }, [query]);
  return match;
}

function SidebarBody(p: Pick<AppShellProps, 'nav' | 'activeNavId' | 'onNav' | 'workspace' | 'onWorkspace' | 'workspaces' | 'user' | 'onLogout'>) {
  const workspaces = p.workspaces ?? [];
  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pt-5 pb-4"><Logo size="sm" /></div>

      {workspaces.length > 0 && (
        <div className="px-4 pb-3">
          <div className="rounded-[14px] p-1" style={{ background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
            <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${workspaces.length}, 1fr)` }}>
              {workspaces.map((w) => {
                const a = p.workspace === w;
                return (
                  <button
                    key={w}
                    onClick={() => p.onWorkspace?.(w)}
                    className="ring-focus rounded-[10px] py-2 text-[13.5px] font-semibold transition"
                    style={{ background: a ? 'var(--brand)' : 'transparent', color: a ? '#fff' : 'var(--muted)', boxShadow: a ? '0 1px 2px rgba(0,0,0,.12)' : 'none' }}
                  >
                    {w}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {p.nav.map((sec) => (
          <div key={sec.label} className="mb-4">
            <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--faint)' }}>{sec.label}</div>
            <div className="space-y-0.5">
              {sec.items.map((it) => {
                const active = p.activeNavId === it.id;
                return (
                  <button
                    key={it.id}
                    onClick={() => p.onNav(it.id)}
                    className="ring-focus flex w-full items-center gap-3 rounded-[12px] px-3 py-2.5 text-[14.5px] font-medium transition"
                    style={{ background: active ? 'var(--brand-soft)' : 'transparent', color: active ? 'var(--brand)' : 'var(--ink-soft)' }}
                  >
                    <Icon name={it.icon} size={20} strokeWidth={active ? 2.1 : 1.9} />
                    <span>{it.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t p-3" style={{ borderColor: 'var(--line)' }}>
        <div className="flex items-center gap-3 rounded-[12px] p-2 transition hover:bg-[var(--surface-2)]">
          <span className="grid h-9 w-9 place-items-center rounded-full font-display text-[13px] font-semibold" style={{ background: 'var(--brand-soft)', color: 'var(--brand)' }}>{p.user.initials}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13.5px] font-semibold" style={{ color: 'var(--ink)' }}>{p.user.name}</span>
            <span className="block truncate text-[12px]" style={{ color: 'var(--muted)' }}>{p.user.email}</span>
          </span>
          <button aria-label="Cerrar sesión" onClick={p.onLogout} className="grid h-8 w-8 place-items-center rounded-lg text-[var(--muted)] transition hover:bg-[var(--surface-3)]">
            <Icon name="logout" size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppShell(props: AppShellProps) {
  const { title, subtitle, tabs, dark, onToggleDark, user, notif = 0, pageActions, children } = props;
  const [drawer, setDrawer] = useState(false);
  const isDesktop = useMedia('(min-width: 1024px)');
  useEffect(() => { if (isDesktop) setDrawer(false); }, [isDesktop]);

  const sidebar = (
    <SidebarBody
      nav={props.nav}
      activeNavId={props.activeNavId}
      onNav={(id) => { props.onNav(id); setDrawer(false); }}
      workspace={props.workspace}
      onWorkspace={props.onWorkspace}
      workspaces={props.workspaces}
      user={user}
      onLogout={props.onLogout}
    />
  );

  return (
    <div className="flex h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      <aside className="hidden w-[260px] shrink-0 border-r lg:block" style={{ background: 'var(--surface)', borderColor: 'var(--line)' }}>
        {sidebar}
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="scrim absolute inset-0" onClick={() => setDrawer(false)} />
          <aside className="drawer-in absolute inset-y-0 left-0 w-[280px] border-r shadow-2xl" style={{ background: 'var(--surface)', borderColor: 'var(--line)' }}>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex h-16 items-center gap-3 border-b px-3 sm:px-5" style={{ borderColor: 'var(--line)' }}>
          <button onClick={() => setDrawer(true)} aria-label="Menú" className="ring-focus grid h-10 w-10 place-items-center rounded-[11px] transition hover:bg-[var(--surface-2)] lg:hidden" style={{ color: 'var(--ink-soft)' }}>
            <Icon name="menu" size={22} />
          </button>
          <h1 className="font-display text-[20px] font-semibold tracking-[-0.02em]" style={{ color: 'var(--ink)' }}>{title}</h1>
          <div className="ml-auto flex items-center gap-1.5">
            <button aria-label="Asistente" className="ring-focus hidden h-10 w-10 place-items-center rounded-[11px] transition hover:bg-[var(--surface-2)] sm:grid" style={{ color: 'var(--ink-soft)' }}>
              <Icon name="sparkle" size={19} />
            </button>
            <button aria-label="Notificaciones" className="ring-focus relative grid h-10 w-10 place-items-center rounded-[11px] transition hover:bg-[var(--surface-2)]" style={{ color: 'var(--ink-soft)' }}>
              <Icon name="bell" size={19} />
              {notif > 0 && <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-bold text-white" style={{ background: 'var(--bad-ink)' }}>{notif}</span>}
            </button>
            <button onClick={onToggleDark} aria-label="Tema" className="ring-focus grid h-10 w-10 place-items-center rounded-[11px] transition hover:bg-[var(--surface-2)]" style={{ color: 'var(--ink-soft)' }}>
              <Icon name={dark ? 'sun' : 'moon'} size={19} />
            </button>
            <button aria-label="Cuenta" className="ring-focus ml-1 grid h-10 w-10 place-items-center rounded-full font-display text-[13px] font-semibold text-white" style={{ background: 'var(--brand)' }}>{user.initials}</button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 pb-32 pt-5 sm:px-6 sm:pt-6">
            {(subtitle || pageActions) && (
              <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                {subtitle && <p className="text-[14.5px]" style={{ color: 'var(--muted)' }}>{subtitle}</p>}
                {pageActions}
              </div>
            )}
            {children}
          </div>
        </main>
      </div>

      {tabs?.items?.length ? (
        <nav className="glass fixed bottom-0 left-0 right-0 z-30 border-t lg:left-[260px]" style={{ borderColor: 'var(--line)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
          <div className="mx-auto flex max-w-3xl items-stretch justify-around">
            {tabs.items.map((it) => {
              const a = it.id === tabs.active;
              return (
                <button
                  key={it.id}
                  onClick={() => tabs.onChange(it.id)}
                  className="ring-focus relative flex flex-1 flex-col items-center gap-1 px-2 pb-2 pt-2.5 transition"
                  style={{ color: a ? 'var(--brand)' : 'var(--muted)' }}
                >
                  {a && <span className="absolute top-0 h-[3px] w-9 rounded-full" style={{ background: 'var(--brand)' }} />}
                  <Icon name={it.icon} size={21} strokeWidth={a ? 2.1 : 1.9} />
                  <span className="text-[11.5px] font-medium leading-none">{it.label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      ) : null}
    </div>
  );
}
