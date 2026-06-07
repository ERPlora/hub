import { useEffect, useMemo, useState } from 'react';
import { IonButton, IonIcon } from '@ionic/react';
import { cubeOutline, storefrontOutline, walletOutline } from 'ionicons/icons';
import {
  LuBox, LuShoppingCart, LuUsers, LuFileText, LuTruck, LuCalendarCheck, LuMessageSquare, LuChartBar,
} from 'react-icons/lu';
import type { IconType } from 'react-icons';
import { PageScaffold } from '@erplora/dashboard-shell';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import { DataTable, type DataTableColumn } from '../components/DataTable';
import { Badge } from '../components/Badge';
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import { useToast } from '../lib/toast';

interface Mod { id: string; name: string; desc: string; price: string; Icon: IconType; installed: boolean; cat: string; }
// "Mis módulos" es el PRIMER tab (ya no es entrada del menú izquierdo).
type MarketplaceTab = 'mine' | 'all' | 'paid';

const MODULES: Mod[] = [
  { id: 'inventory', name: 'Inventario', desc: 'Productos, stock y movimientos', price: 'Gratis', Icon: LuBox, installed: true, cat: 'Operación' },
  { id: 'pos', name: 'TPV / POS', desc: 'Punto de venta y caja', price: 'Gratis', Icon: LuShoppingCart, installed: true, cat: 'Ventas' },
  { id: 'customers', name: 'Clientes (CRM)', desc: 'Fichas, grupos y actividad', price: 'Gratis', Icon: LuUsers, installed: true, cat: 'Ventas' },
  { id: 'invoice', name: 'Facturación', desc: 'Facturas y rectificativas', price: '9 €/mes', Icon: LuFileText, installed: false, cat: 'Finanzas' },
  { id: 'couriers', name: 'Envíos', desc: 'Integración con transportistas', price: '12 €/mes', Icon: LuTruck, installed: false, cat: 'Logística' },
  { id: 'appointments', name: 'Reservas', desc: 'Agenda y citas online', price: '7 €/mes', Icon: LuCalendarCheck, installed: false, cat: 'Operación' },
  { id: 'messaging', name: 'Mensajería', desc: 'WhatsApp y email unificados', price: '15 €/mes', Icon: LuMessageSquare, installed: false, cat: 'Comunicación' },
  { id: 'analytics', name: 'Analítica', desc: 'Cuadros de mando e informes', price: '9 €/mes', Icon: LuChartBar, installed: false, cat: 'BI' },
];

const tabs: Array<PageTabBarItem<MarketplaceTab>> = [
  { value: 'mine', label: 'Mis módulos', icon: <IonIcon icon={cubeOutline} /> },
  { value: 'all', label: 'Catálogo', icon: <IonIcon icon={storefrontOutline} /> },
  { value: 'paid', label: 'Pago', icon: <IonIcon icon={walletOutline} /> },
];

function iconForModule(id: string, category: string): IconType {
  const key = `${id} ${category}`.toLowerCase();
  if (key.includes('pos') || key.includes('tpv') || key.includes('venta')) return LuShoppingCart;
  if (key.includes('client') || key.includes('crm')) return LuUsers;
  if (key.includes('fact') || key.includes('invoice')) return LuFileText;
  if (key.includes('env') || key.includes('courier') || key.includes('log')) return LuTruck;
  if (key.includes('reserva') || key.includes('agenda') || key.includes('appointment')) return LuCalendarCheck;
  if (key.includes('message') || key.includes('whatsapp') || key.includes('comun')) return LuMessageSquare;
  if (key.includes('analytic') || key.includes('bi')) return LuChartBar;
  return LuBox;
}

function toViewModule(module: CloudMarketplaceModule): Mod {
  return {
    id: module.id,
    name: module.name,
    desc: module.description,
    price: module.priceLabel || 'Consultar',
    Icon: iconForModule(module.id, module.category),
    installed: module.installed,
    cat: module.category,
  };
}

export function MarketplacePage() {
  const [tab, setTab] = useState<MarketplaceTab>('mine');
  const [modules, setModules] = useState<Mod[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const cloudModules = await cloudMarketplaceModules();
        if (!cancelled) setModules(cloudModules.map(toViewModule));
      } catch (error) {
        if (!config.demo) throw error;
        if (!cancelled) setModules(MODULES);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })().catch(() => {
      if (!cancelled) { setModules([]); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, []);

  const rows = useMemo(() => modules.filter((m) => (
    tab === 'mine' ? m.installed : tab === 'paid' ? m.price !== 'Gratis' : true
  )), [modules, tab]);

  const columns: Array<DataTableColumn<Mod>> = [
    {
      key: 'name', header: 'Módulo', width: 'minmax(12rem,1.5fr)',
      cell: (m) => (
        <span className="flex items-center gap-2.5">
          <m.Icon size={18} className="shrink-0 text-[color:var(--ion-color-primary)]" />
          <span className="truncate font-medium">{m.name}</span>
        </span>
      ),
      value: (m) => m.name,
    },
    { key: 'desc', header: 'Descripción', width: 'minmax(12rem,2fr)' },
    { key: 'cat', header: 'Categoría', filter: 'select', width: '10rem' },
    {
      key: 'price', header: 'Precio', filter: 'select', width: '8rem',
      cell: (m) => <Badge tone={m.price === 'Gratis' ? 'success' : 'neutral'}>{m.price}</Badge>,
    },
  ];

  const action = (m: Mod) =>
    m.installed ? (
      <IonButton fill="outline" size="small" disabled>Instalado</IonButton>
    ) : (
      <IonButton size="small" onClick={() => toast(`Instalando ${m.name}…`, { color: 'primary' })}>Instalar</IonButton>
    );

  return (
    <PageScaffold title="Marketplace" footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}>
      <div className="flex h-full flex-col">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(m) => m.id}
          title={tab === 'mine' ? 'Mis módulos' : tab === 'paid' ? 'Módulos de pago' : 'Catálogo'}
          loading={loading}
          pageSize={12}
          defaultView="card"
          emptyMessage={tab === 'mine' ? 'No tienes módulos instalados' : 'Sin módulos'}
          rowActions={action}
          cardIcon={(m) => <m.Icon size={18} />}
          cardTitle={(m) => m.name}
          renderCard={(m) => (
            <div className="flex flex-col gap-2 p-4">
              <Badge>{m.cat}</Badge>
              <p className="text-sm text-[color:var(--ion-color-medium)]">{m.desc}</p>
              <div className="mt-1">
                <Badge tone={m.price === 'Gratis' ? 'success' : 'neutral'}>{m.price}</Badge>
              </div>
            </div>
          )}
        />
      </div>
    </PageScaffold>
  );
}

export default MarketplacePage;
