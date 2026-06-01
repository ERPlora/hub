import { useState } from 'react';
import {
  IonLabel, IonCard, IonCardContent, IonList, IonItem, IonChip,
  IonButton, IonNote, IonProgressBar,
} from '@ionic/react';
import {
  LuActivity, LuCpu, LuMemoryStick, LuDatabase, LuPlugZap,
  LuMonitor, LuApple, LuTerminal, LuCircleCheck, LuRefreshCw,
  LuDatabaseBackup, LuScrollText, LuDownload,
} from 'react-icons/lu';
import type { IconType } from 'react-icons';
import { PageScaffold } from '../components/PageScaffold';
import { PagePanel } from '../components/PagePanel';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import { useToast } from '../lib/toast';

type Tab = 'resources' | 'updates' | 'backups' | 'logs';

const tabs: Array<PageTabBarItem<Tab>> = [
  { value: 'resources', label: 'Recursos', icon: <LuActivity size={22} /> },
  { value: 'updates', label: 'Actualizaciones', icon: <LuRefreshCw size={22} /> },
  { value: 'backups', label: 'Copias', icon: <LuDatabaseBackup size={22} /> },
  { value: 'logs', label: 'Registros', icon: <LuScrollText size={22} /> },
];

// Métricas de recursos del hub (demo). En producción → runtime/Cloud.
interface Metric {
  label: string;
  value: string;
  unit?: string;
  Icon: IconType;
  progress?: number;
}

const METRICS: Metric[] = [
  { label: 'RAM', value: '612 MB', unit: 'de 2 GB', Icon: LuMemoryStick, progress: 0.3 },
  { label: 'CPU', value: '0,4 cores', unit: '2 vCPU', Icon: LuCpu, progress: 0.2 },
  { label: 'Base de datos', value: '8,6 MB', unit: 'Aurora DB', Icon: LuDatabase },
  { label: 'Conexiones BD', value: '12', unit: '/ 120', Icon: LuPlugZap, progress: 0.1 },
];

const BRIDGE_OS: Array<{ label: string; Icon: IconType }> = [
  { label: 'Windows', Icon: LuMonitor },
  { label: 'macOS', Icon: LuApple },
  { label: 'Linux', Icon: LuTerminal },
];

export function SystemPage() {
  const [tab, setTab] = useState<Tab>('resources');
  const { toast } = useToast();

  return (
    <PageScaffold title="Sistema" footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}>
      {tab === 'resources' && (
        <PagePanel>
          {/* Uso de recursos */}
          <div className="erplora-kpi-grid">
            {METRICS.map((m) => (
              <IonCard key={m.label} className="settings-card ion-no-margin">
                <IonCardContent>
                  <div className="erplora-kpi">
                    <div className="erplora-kpi__top">
                      <span className="erplora-kpi__label">{m.label}</span>
                      <span className="erplora-kpi-icon"><m.Icon size={20} /></span>
                    </div>
                    <span className="erplora-kpi__value">
                      {m.value}{' '}
                      {m.unit && <small className="erplora-kpi__unit">{m.unit}</small>}
                    </span>
                    {m.progress !== undefined && (
                      <IonProgressBar value={m.progress} className="mt-2" />
                    )}
                  </div>
                </IonCardContent>
              </IonCard>
            ))}
          </div>

          {/* Conexión Bridge */}
          <IonCard className="settings-card ion-no-margin">
            <IonCardContent>
              <div className="erplora-card-header">
                <h3>Conexión Bridge</h3>
                <IonChip color="medium" className="ion-no-margin">Desconectado</IonChip>
              </div>
              <p className="erplora-muted erplora-text-sm" style={{ margin: 0 }}>
                El cliente Bridge no está corriendo en este equipo. Vincula un Bridge
                abajo para gestionar el hardware — tus impresoras, cajón y escáneres
                aparecerán aquí.
              </p>

              <ol className="erplora-steps">
                {['Descargar', 'Instalar', 'Vincular', 'Configurar'].map((s, i) => (
                  <li key={s} className="erplora-step">
                    <span className={`erplora-avatar erplora-avatar--sm${i === 0 ? '' : ' erplora-step__num--muted'}`}>
                      {i + 1}
                    </span>
                    <span className="erplora-text-sm">{s}</span>
                  </li>
                ))}
              </ol>

              <div className="erplora-bridge-download">
                <div className="erplora-feed__primary">Descargar ERPlora Bridge</div>
                <div className="erplora-feed__sub" style={{ marginBottom: 12 }}>
                  Bridge es una pequeña app nativa que conecta este hub con tus
                  impresoras, cajón y escáneres. Elige tu sistema para continuar.
                </div>
                <div className="erplora-os-grid">
                  {BRIDGE_OS.map((os) => (
                    <IonButton
                      key={os.label}
                      fill="outline"
                      onClick={() => toast(`Descargando Bridge para ${os.label}…`, { color: 'primary' })}
                    >
                      <os.Icon size={18} className="mr-2" />
                      {os.label}
                    </IonButton>
                  ))}
                </div>
              </div>
            </IonCardContent>
          </IonCard>
        </PagePanel>
      )}

      {tab === 'updates' && (
        <PagePanel bodyClassName="flex flex-col items-center gap-3 py-12 text-center">
          <span className="erplora-empty-icon erplora-empty-icon--success">
            <LuCircleCheck size={26} />
          </span>
          <strong className="text-lg">Estás al día</strong>
          <p className="erplora-muted erplora-mono m-0">Hub v3.4 · comprobado ahora</p>
          <IonButton fill="outline" onClick={() => toast('Buscando actualizaciones…', { color: 'primary' })}>
            <LuRefreshCw size={16} className="mr-2" />Buscar actualizaciones
          </IonButton>
        </PagePanel>
      )}

      {tab === 'backups' && (
        <PagePanel>
          <div className="erplora-card-header">
              <h3>Copias automáticas</h3>
              <IonButton size="small" onClick={() => toast('Creando copia…', { color: 'primary' })}>
                <LuDatabaseBackup size={16} className="mr-1" />Copia ahora
              </IonButton>
            </div>
            <div className="mb-3">
              <p className="erplora-feed__sub mb-1">Almacenamiento usado · 2,1 GB / 8 GB</p>
              <IonProgressBar value={0.26} />
            </div>
            <IonList>
              {['2026-05-30 03:00', '2026-05-29 03:00', '2026-05-28 03:00'].map((when, i, arr) => (
                <IonItem key={when} lines={i === arr.length - 1 ? 'none' : 'inset'}>
                  <span slot="start" className="text-[color:var(--ion-color-medium)]"><LuDatabase size={20} /></span>
                  <IonLabel>
                    <h2 className="font-semibold">Copia diaria</h2>
                    <IonNote className="erplora-mono">{when} · 8,6 MB</IonNote>
                  </IonLabel>
                  <IonButton slot="end" fill="clear" aria-label="Descargar">
                    <LuDownload size={18} />
                  </IonButton>
                </IonItem>
              ))}
          </IonList>
        </PagePanel>
      )}

      {tab === 'logs' && (
        <PagePanel>
          <h3 className="erplora-card-title">Registro de eventos</h3>
          <IonList>
              {[
                { when: '03:00:01', lvl: 'INFO', msg: 'backup.completed', meta: 'size=8.6MB' },
                { when: '02:14:55', lvl: 'INFO', msg: 'module.sync', meta: 'ok' },
                { when: '01:58:12', lvl: 'WARN', msg: 'bridge.disconnected', meta: 'retry=3' },
                { when: '01:40:03', lvl: 'INFO', msg: 'auth.login', meta: 'user=demo@erplora.com' },
                { when: '00:12:44', lvl: 'INFO', msg: 'invoice.issued', meta: 'INV-2026-00034' },
              ].map((l, i, arr) => (
                <IonItem key={i} lines={i === arr.length - 1 ? 'none' : 'inset'}>
                  <IonNote slot="start" className="erplora-mono w-[78px] text-[12px]">[{l.when}]</IonNote>
                  <IonChip color={l.lvl === 'WARN' ? 'warning' : 'medium'} className="ion-no-margin">{l.lvl}</IonChip>
                  <IonLabel className="ion-text-wrap erplora-mono ml-2 text-[12.5px]">
                    {l.msg} <span className="erplora-muted">{l.meta}</span>
                  </IonLabel>
                </IonItem>
              ))}
          </IonList>
        </PagePanel>
      )}
    </PageScaffold>
  );
}
