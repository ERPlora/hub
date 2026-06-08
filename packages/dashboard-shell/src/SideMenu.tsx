// Menú lateral del shell: marca + navegación (por datos) + footer de cuenta.
// No conoce auth ni rutas concretas: todo entra por `menu`, `branding` e `identity`.
import {
  IonMenu, IonHeader, IonToolbar, IonContent, IonList, IonItem, IonLabel,
  IonListHeader, IonMenuToggle, IonFooter, IonActionSheet,
} from '@ionic/react';
import { useRef, type ChangeEvent } from 'react';
import { useLocation } from 'react-router-dom';
import { cameraOutline, trashOutline, settingsOutline, logOutOutline } from 'ionicons/icons';
import { Avatar } from './Avatar';
import { useLocalAvatar, fileToAvatarDataUrl } from './localAvatar';
import type { NavSection, ShellBranding, ShellIdentity } from './types';

interface SideMenuProps {
  menu: NavSection[];
  branding: ShellBranding;
  identity: ShellIdentity;
}

export function SideMenu({ menu, branding, identity }: SideMenuProps) {
  const location = useLocation();
  const { user, onLogout, onOpenSettings } = identity;
  const [localAvatar, setLocalAvatar] = useLocalAvatar(user?.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLIonMenuElement>(null);

  // La foto LOCAL (de este dispositivo) tiene preferencia; si no, la remota.
  const avatarSrc = localAvatar ?? user?.avatarUrl ?? null;

  const onPickFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // permite re-elegir el mismo archivo
    if (!file) return;
    try {
      setLocalAvatar(await fileToAvatarDataUrl(file));
    } catch {
      // Imagen no procesable: no rompemos la UI, se mantiene el avatar actual.
    }
  };

  return (
    <IonMenu ref={menuRef} contentId="main" type="overlay">
      <IonHeader className="ion-no-border">
        <IonToolbar className="ion-no-border">
          <div className="erplora-logo-pad">{branding.logo}</div>
          {branding.switcher && <div className="px-3 pb-3">{branding.switcher}</div>}
        </IonToolbar>
      </IonHeader>
      <IonContent>
        {menu.map((section) => (
          <IonList key={section.label} className="erplora-nav-list">
            <IonListHeader>
              <IonLabel className="erplora-section-label">{section.label}</IonLabel>
            </IonListHeader>
            {section.items.map(({ path, label, Icon }) => (
              <IonMenuToggle key={path} autoHide={false}>
                <IonItem
                  routerLink={path}
                  routerDirection="root"
                  detail={false}
                  lines="none"
                  className={[
                    'erplora-nav-item',
                    location.pathname === path ? 'erplora-nav-item-active' : '',
                  ].join(' ')}
                >
                  <span slot="start" className="flex items-center"><Icon size={20} /></span>
                  <IonLabel>{label}</IonLabel>
                </IonItem>
              </IonMenuToggle>
            ))}
          </IonList>
        ))}
      </IonContent>
      <IonFooter className="ion-no-border">
        <IonToolbar className="ion-no-border">
          {/* Identidad + acceso a la cuenta. El boton abre el menú (Ajustes / salir). */}
          <IonItem
            button
            detail={false}
            lines="none"
            className="erplora-nav-item"
            id="erplora-account-trigger"
          >
            <span slot="start">
              <Avatar name={user?.name ?? '?'} src={avatarSrc} />
            </span>
            <IonLabel>
              <h3 className="font-bold">{user?.name}</h3>
              {user?.email && <p className="text-xs opacity-60">{user.email}</p>}
            </IonLabel>
          </IonItem>
        </IonToolbar>

        <IonActionSheet
          trigger="erplora-account-trigger"
          header={user?.name}
          subHeader={user?.email ?? undefined}
          buttons={[
            // Foto LOCAL de este dispositivo (no se sube a ningún sitio).
            {
              text: localAvatar ? 'Cambiar foto local' : 'Subir foto local',
              icon: cameraOutline,
              handler: () => { fileRef.current?.click(); },
            },
            ...(localAvatar
              ? [{
                  text: 'Quitar foto local',
                  icon: trashOutline,
                  role: 'destructive' as const,
                  handler: () => { setLocalAvatar(null); },
                }]
              : []),
            {
              text: 'Ajustes',
              icon: settingsOutline,
              handler: () => { menuRef.current?.close(); onOpenSettings(); },
            },
            {
              text: 'Cerrar sesión',
              icon: logOutOutline,
              role: 'destructive' as const,
              handler: () => { onLogout(); },
            },
            { text: 'Cancelar', role: 'cancel' as const },
          ]}
        />

        {/* Input oculto para elegir la foto local. */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={onPickFile}
        />
      </IonFooter>
    </IonMenu>
  );
}
