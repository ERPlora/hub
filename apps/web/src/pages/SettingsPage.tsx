import { useState } from 'react';
import { IonButton } from '@ionic/react';
import {
  LuBuilding2,
  LuGlobe,
  LuLanguages,
  LuPalette,
  LuPanelLeft,
  LuPlug,
  LuSave,
  LuStore,
  LuTicket,
  LuWalletCards,
} from 'react-icons/lu';
import { PageScaffold } from '@erplora/dashboard-shell';
import { PagePanel } from '../components/PagePanel';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import {
  SettingsCard,
  SettingsList,
  SettingsNavigationRow,
  SettingsSelectRow,
  SettingsToggleRow,
} from '../components/settings/SettingsBlocks';
import { useToast } from '../lib/toast';
import { useTheme, type ThemeMode } from '../lib/theme';

type Tab = 'hub' | 'store' | 'tax' | 'tickets';

const tabs: Array<PageTabBarItem<Tab>> = [
  { value: 'hub', label: 'Hub', icon: <LuBuilding2 size={23} /> },
  { value: 'store', label: 'Store', icon: <LuStore size={23} /> },
  { value: 'tax', label: 'Tax', icon: <LuWalletCards size={23} /> },
  { value: 'tickets', label: 'Tickets', icon: <LuTicket size={23} /> },
];

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('hub');
  const { toast } = useToast();
  const { setMode } = useTheme();

  return (
    <PageScaffold
      title="Ajustes del Hub"
      footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}
    >
      {tab === 'hub' && (
        <PagePanel>
          <SettingsCard>
            <SettingsList>
              <SettingsSelectRow
                icon={LuLanguages}
                title="System Language"
                description="Default language for the Hub interface"
                value="es"
                options={[
                  { value: 'es', label: 'Espanol' },
                  { value: 'en', label: 'English' },
                ]}
              />
              <SettingsSelectRow
                icon={LuGlobe}
                title="Timezone"
                description="Timezone for dates and schedules"
                value="madrid"
                options={[
                  { value: 'madrid', label: 'Europe/Madrid' },
                  { value: 'canary', label: 'Atlantic/Canary' },
                ]}
              />
              <SettingsSelectRow
                icon={LuBuilding2}
                title="Country"
                description="Country for regional settings"
                value="spain"
                options={[
                  { value: 'spain', label: 'Spain' },
                  { value: 'portugal', label: 'Portugal' },
                ]}
              />
              <SettingsSelectRow
                icon={LuPalette}
                title="Theme"
                description="Appearance mode for the interface"
                value="system"
                onChange={(value) => setMode(value as ThemeMode)}
                options={[
                  { value: 'system', label: 'System (auto)' },
                  { value: 'light', label: 'Light' },
                  { value: 'dark', label: 'Dark' },
                ]}
              />
            </SettingsList>
          </SettingsCard>

          <IonButton
            className="settings-save-button"
            onClick={() => toast('Hub settings saved', { color: 'success' })}
          >
            <LuSave className="mr-2" size={18} />
            Guardar ajustes
          </IonButton>

          <SettingsToggleRow
            icon={LuPanelLeft}
            title="Show modules in sidebar"
            description="Display installed modules as shortcuts in the sidebar navigation"
          />

          <h2 className="settings-section-title mt-2">Hardware</h2>
          <SettingsNavigationRow
            icon={LuPlug}
            title="ERPlora Bridge"
            description="Printers, cash drawer, barcode scanner and bridge connection"
            status="Disabled"
          />
        </PagePanel>
      )}

      {tab === 'store' && (
        <PagePanel>
          <SettingsCard>
            <SettingsList>
              <SettingsSelectRow icon={LuStore} title="Store Type" description="Default sales workflow" value="retail" options={[{ value: 'retail', label: 'Retail' }, { value: 'food', label: 'Food Service' }]} />
              <SettingsSelectRow icon={LuGlobe} title="Locale" description="Regional display format" value="es" options={[{ value: 'es', label: 'Spain' }, { value: 'en', label: 'United Kingdom' }]} />
            </SettingsList>
          </SettingsCard>
        </PagePanel>
      )}

      {tab === 'tax' && (
        <PagePanel>
          <SettingsCard>
            <SettingsList>
              <SettingsSelectRow
                icon={LuWalletCards}
                title="IVA por defecto"
                description="Tipo aplicado a productos nuevos"
                value="21"
                options={[
                  { value: '21', label: '21% (general)' },
                  { value: '10', label: '10% (reducido)' },
                  { value: '4', label: '4% (superreducido)' },
                ]}
              />
              <SettingsSelectRow
                icon={LuBuilding2}
                title="Régimen fiscal"
                description="Régimen de facturación"
                value="general"
                options={[
                  { value: 'general', label: 'Régimen general' },
                  { value: 'recargo', label: 'Recargo de equivalencia' },
                ]}
              />
            </SettingsList>
          </SettingsCard>

          <SettingsToggleRow
            icon={LuTicket}
            title="VeriFactu"
            description="Reporte de facturas conforme a la normativa"
            checked
          />

          <IonButton
            className="settings-save-button"
            onClick={() => toast('Ajustes fiscales guardados', { color: 'success' })}
          >
            <LuSave className="mr-2" size={18} />
            Guardar cambios
          </IonButton>
        </PagePanel>
      )}

      {tab === 'tickets' && (
        <PagePanel>
          <SettingsNavigationRow icon={LuTicket} title="Ticket Template" description="Printed and digital receipt settings" />
        </PagePanel>
      )}
    </PageScaffold>
  );
}
