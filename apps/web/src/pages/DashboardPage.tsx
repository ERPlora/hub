import { useEffect, useState } from 'react';
import { useHistory } from 'react-router-dom';
import {
  IonBadge,
  IonButton,
  IonCard,
  IonCardContent,
  IonSpinner,
} from '@ionic/react';
import type { IconType } from 'react-icons';
import {
  LuActivity,
  LuBoxes,
  LuContact,
  LuCpu,
  LuFileText,
  LuGauge,
  LuLayoutGrid,
  LuPlus,
  LuReceipt,
  LuScanLine,
  LuTrendingDown,
  LuTrendingUp,
  LuTriangleAlert,
  LuUsers,
} from 'react-icons/lu';
import { PageScaffold } from '../components/PageScaffold';
import { PagePanel } from '../components/PagePanel';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import { loadMenu, type MenuEntry } from '../module-loader';

type Tab = 'resumen' | 'apps' | 'actividad';

const tabs: Array<PageTabBarItem<Tab>> = [
  { value: 'resumen', label: 'Resumen', icon: <LuGauge size={22} /> },
  { value: 'apps', label: 'Aplicaciones', icon: <LuLayoutGrid size={22} /> },
  { value: 'actividad', label: 'Actividad', icon: <LuActivity size={22} /> },
];

// KPIs de cabecera. Demo por ahora; en producción vendrán del runtime / módulos.
interface Kpi {
  label: string;
  value: string;
  Icon: IconType;
  sub?: string;
  trend?: 'up' | 'down';
}

const KPIS: Kpi[] = [
  { label: 'Ventas hoy', value: '€4 812', Icon: LuTrendingUp, sub: '+12,4% vs ayer', trend: 'up' },
  { label: 'Pedidos', value: '183', Icon: LuReceipt, sub: '+9 en la última hora', trend: 'up' },
  { label: 'Personal activo', value: '6', Icon: LuUsers, sub: '2 en caja ahora' },
  { label: 'Stock bajo', value: '7', Icon: LuTriangleAlert, sub: 'bajo umbral', trend: 'down' },
];

// Mapa icono por clave de nav del módulo (react-icons, homogéneo con el resto del shell).
const MODULE_ICONS: Record<string, IconType> = {
  pos: LuScanLine,
  cash: LuScanLine,
  people: LuUsers,
  customers: LuContact,
  invoice: LuFileText,
  document: LuFileText,
  cube: LuBoxes,
};

function moduleIcon(entry: MenuEntry): IconType {
  return MODULE_ICONS[entry.nav.icon ?? ''] ?? LuBoxes;
}

interface FeedItem {
  primary: string;
  sub: string;
  tone: 'success' | 'warning' | 'primary';
}

const FEED: FeedItem[] = [
  { primary: 'Pedido #1042 cerrado', sub: '38,90 € · tarjeta · caja 1', tone: 'success' },
  { primary: 'Alerta de stock · Cola 33cl', sub: 'bajo umbral (quedan 4)', tone: 'warning' },
  { primary: 'Lucía García fichó entrada', sub: 'caja 2', tone: 'primary' },
  { primary: 'Factura INV-2026-00018 pagada', sub: '29,99 €', tone: 'success' },
];

export function DashboardPage() {
  const history = useHistory();
  const [tab, setTab] = useState<Tab>('resumen');
  const [modules, setModules] = useState<MenuEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadMenu()
      .then((entries) => {
        if (!cancelled) setModules(entries);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageScaffold title="Dashboard" footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}>
      {tab === 'resumen' && (
        <PagePanel>
          {/* KPIs */}
          <div className="erplora-kpi-grid">
            {KPIS.map((k) => (
              <IonCard key={k.label} className="settings-card ion-no-margin">
                <IonCardContent>
                  <div className="erplora-kpi">
                    <div className="erplora-kpi__top">
                      <span className="erplora-kpi__label">{k.label}</span>
                      <span className="erplora-kpi-icon">
                        <k.Icon size={20} />
                      </span>
                    </div>
                    <span className="erplora-kpi__value">{k.value}</span>
                    {k.sub && (
                      <span className={`erplora-kpi__sub${k.trend ? ` is-${k.trend}` : ''}`}>
                        {k.trend === 'up' && <LuTrendingUp size={14} />}
                        {k.trend === 'down' && <LuTrendingDown size={14} />}
                        {k.sub}
                      </span>
                    )}
                  </div>
                </IonCardContent>
              </IonCard>
            ))}
          </div>

          {/* Estado del terminal */}
          <IonCard className="settings-card ion-no-margin">
            <IonCardContent>
              <h2 className="erplora-card-title">Este terminal</h2>
              <dl className="erplora-kv">
                <dt>Plan</dt>
                <dd className="erplora-mono">Starter</dd>
                <dt>Estado</dt>
                <dd>
                  <IonBadge color="success">Activo</IonBadge>
                </dd>
                <dt>Próxima factura</dt>
                <dd className="erplora-mono">13 jun 2026</dd>
                <dt>Bridge</dt>
                <dd>
                  <IonBadge color="medium">Desconectado</IonBadge>
                </dd>
              </dl>
              <IonButton expand="block" fill="outline" onClick={() => history.push('/system')}>
                <LuCpu size={18} style={{ marginRight: 8 }} /> Abrir sistema
              </IonButton>
            </IonCardContent>
          </IonCard>
        </PagePanel>
      )}

      {tab === 'apps' && (
        <PagePanel>
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-[color:var(--ion-color-medium)]">
              <IonSpinner name="crescent" /> Cargando módulos…
            </div>
          ) : (
            <div className="erplora-tile-grid">
              {modules.map((entry) => {
                const Icon = moduleIcon(entry);
                return (
                  <IonCard
                    key={`${entry.moduleId}:${entry.nav.id}`}
                    button
                    className="settings-card ion-no-margin"
                    onClick={() => history.push(`/m/${entry.moduleId}`)}
                  >
                    <IonCardContent className="flex min-h-28 flex-col items-center justify-center gap-3 text-center">
                      <span className="erplora-kpi-icon">
                        <Icon size={22} />
                      </span>
                      <strong>{entry.nav.label}</strong>
                    </IonCardContent>
                  </IonCard>
                );
              })}
              <IonCard
                button
                className="settings-card ion-no-margin"
                onClick={() => history.push('/marketplace')}
              >
                <IonCardContent className="flex min-h-28 flex-col items-center justify-center gap-3 text-center">
                  <span className="erplora-kpi-icon">
                    <LuPlus size={22} />
                  </span>
                  <strong>Añadir módulo</strong>
                </IonCardContent>
              </IonCard>
            </div>
          )}
        </PagePanel>
      )}

      {tab === 'actividad' && (
        <PagePanel>
          <h2 className="erplora-card-title">Actividad reciente</h2>
          <ul className="erplora-feed">
            {FEED.map((f) => (
              <li key={f.primary}>
                <span className={`erplora-feed__dot is-${f.tone}`} />
                <div>
                  <div className="erplora-feed__primary">{f.primary}</div>
                  <div className="erplora-feed__sub">{f.sub}</div>
                </div>
              </li>
            ))}
          </ul>
        </PagePanel>
      )}
    </PageScaffold>
  );
}
