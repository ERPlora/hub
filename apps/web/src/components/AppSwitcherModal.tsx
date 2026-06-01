// App switcher: modal con todas las apps/módulos instalados (grid). Las apps a las que el
// usuario NO tiene acceso aparecen deshabilitadas (con candado). Patrón espejo del asistente.
//
// Acceso (demo): se usa el campo real `isAdmin` de useAuth — las apps administrativas quedan
// disabled para no-admin. Cuando el runtime exponga permisos finos, sustituir `canAccess`
// por `auth.hasPermission(app.permission)` (ARQUITECTURA.md §9.2; mismo gate que UI/API/IA).
import { IonModal, IonHeader, IonToolbar, IonTitle, IonButtons, IonButton, IonContent } from '@ionic/react';
import { useHistory } from 'react-router-dom';
import type { IconType } from 'react-icons';
import {
  LuGrid2X2, LuX, LuLock, LuLayoutDashboard, LuUsers, LuShield, LuFileText,
  LuStore, LuPackage, LuCpu, LuSettings,
} from 'react-icons/lu';
import { useAuth } from '../lib/auth';

interface AppEntry {
  path: string;
  label: string;
  Icon: IconType;
  /** Si true, solo accesible por administradores (demo). */
  adminOnly?: boolean;
}

// Catálogo de apps instaladas (en producción vendría de /api/modules del runtime).
const APPS: AppEntry[] = [
  { path: '/', label: 'Dashboard', Icon: LuLayoutDashboard },
  { path: '/employees', label: 'Empleados', Icon: LuUsers },
  { path: '/roles', label: 'Roles', Icon: LuShield, adminOnly: true },
  { path: '/billing', label: 'Billing', Icon: LuFileText, adminOnly: true },
  { path: '/marketplace', label: 'Marketplace', Icon: LuStore },
  { path: '/modules', label: 'Mis módulos', Icon: LuPackage },
  { path: '/system', label: 'Sistema', Icon: LuCpu, adminOnly: true },
  { path: '/settings', label: 'Ajustes', Icon: LuSettings, adminOnly: true },
];

export function AppSwitcherModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const history = useHistory();
  const { user } = useAuth();
  const isAdmin = user?.isAdmin ?? false;
  const canAccess = (app: AppEntry) => !app.adminOnly || isAdmin;

  function openApp(app: AppEntry) {
    if (!canAccess(app)) return;
    history.push(app.path);
    onClose();
  }

  return (
    <IonModal isOpen={isOpen} onDidDismiss={onClose} className="erplora-appswitcher">
      <IonHeader>
        <IonToolbar className="ion-no-border">
          <IonButtons slot="start">
            <span className="ml-3 text-[color:var(--ion-color-primary)]"><LuGrid2X2 size={20} /></span>
          </IonButtons>
          <IonTitle>Aplicaciones</IonTitle>
          <IonButtons slot="end">
            <IonButton onClick={onClose} aria-label="Cerrar"><LuX size={20} /></IonButton>
          </IonButtons>
        </IonToolbar>
      </IonHeader>
      <IonContent className="ion-padding">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {APPS.map((app) => {
            const enabled = canAccess(app);
            return (
              <button
                key={app.path}
                type="button"
                disabled={!enabled}
                onClick={() => openApp(app)}
                aria-label={enabled ? app.label : `${app.label} (sin acceso)`}
                className="relative flex aspect-square flex-col items-center justify-center gap-2 rounded-2xl border p-2 text-center transition disabled:cursor-not-allowed disabled:opacity-40 enabled:hover:border-[color:var(--ion-color-primary)] enabled:hover:bg-[color:var(--ion-color-step-50)]"
                style={{ borderColor: 'var(--ion-border-color)', background: 'var(--ion-item-background)' }}
              >
                <span
                  className="grid h-12 w-12 place-items-center rounded-xl"
                  style={{
                    background: enabled ? 'rgba(20,150,214,.12)' : 'var(--ion-color-step-100)',
                    color: enabled ? 'var(--ion-color-primary)' : 'var(--ion-color-medium)',
                  }}
                >
                  <app.Icon size={24} />
                </span>
                <span className="text-[12.5px] font-medium leading-tight" style={{ color: 'var(--ion-text-color)' }}>
                  {app.label}
                </span>
                {!enabled && (
                  <span
                    className="absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full"
                    style={{ background: 'var(--ion-color-step-150)', color: 'var(--ion-color-medium)' }}
                    title="Sin acceso"
                  >
                    <LuLock size={12} />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </IonContent>
    </IonModal>
  );
}
