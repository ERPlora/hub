import { useEffect, useState } from 'react';
import { IonButton, IonIcon } from '@ionic/react';
import { receiptOutline, refreshOutline, cardOutline } from 'ionicons/icons';
import { LuDownload, LuFileText, LuCreditCard } from 'react-icons/lu';
import { PageScaffold } from '@erplora/dashboard-shell';
import { PageTabBar, type PageTabBarItem } from '../components/PageTabBar';
import { DataTable, type DataTableColumn } from '../components/DataTable';
import { Badge, type BadgeTone } from '../components/Badge';
import { config } from '../lib/config';
import {
  cloudInvoices, cloudSubscriptions, getAccessToken,
  type CloudInvoice, type CloudSubscription,
} from '../lib/cloud';

type BillingTab = 'invoices' | 'subscriptions' | 'payments';

const tabs: Array<PageTabBarItem<BillingTab>> = [
  { value: 'invoices', label: 'Facturas', icon: <IonIcon icon={receiptOutline} /> },
  { value: 'subscriptions', label: 'Suscripciones', icon: <IonIcon icon={refreshOutline} /> },
  { value: 'payments', label: 'Pagos', icon: <IonIcon icon={cardOutline} /> },
];

const fmtDate = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
const fmtMoney = (n: number, currency: string) =>
  new Intl.NumberFormat('es-ES', { style: 'currency', currency: currency || 'EUR' }).format(n);

// Estado de factura/suscripción del Cloud (StatusD51Enum) → etiqueta + tono.
const STATUS_LABEL: Record<CloudInvoice['status'], string> = {
  draft: 'Borrador', open: 'Abierta', paid: 'Pagada', void: 'Anulada', uncollectible: 'Incobrable',
};
const STATUS_TONE: Record<CloudInvoice['status'], BadgeTone> = {
  draft: 'neutral', open: 'warning', paid: 'success', void: 'neutral', uncollectible: 'danger',
};

export function BillingPage() {
  const [tab, setTab] = useState<BillingTab>('invoices');
  const [invoices, setInvoices] = useState<CloudInvoice[]>([]);
  const [subscriptions, setSubscriptions] = useState<CloudSubscription[]>([]);
  const [loadingInvoices, setLoadingInvoices] = useState(true);
  const [loadingSubs, setLoadingSubs] = useState(true);

  useEffect(() => {
    let cancelled = false;
    cloudInvoices()
      .then((data) => { if (!cancelled) setInvoices(data); })
      .catch(() => { if (!cancelled) setInvoices([]); })
      .finally(() => { if (!cancelled) setLoadingInvoices(false); });
    cloudSubscriptions()
      .then((data) => { if (!cancelled) setSubscriptions(data); })
      .catch(() => { if (!cancelled) setSubscriptions([]); })
      .finally(() => { if (!cancelled) setLoadingSubs(false); });
    return () => { cancelled = true; };
  }, []);

  const invoiceColumns: Array<DataTableColumn<CloudInvoice>> = [
    { key: 'number', header: 'Factura', width: 'minmax(10rem,1fr)' },
    { key: 'issueDate', header: 'Fecha', filter: 'dateRange', width: '8.5rem', cell: (r) => fmtDate(r.issueDate) },
    { key: 'dueDate', header: 'Vencimiento', filter: 'dateRange', width: '9rem', cell: (r) => fmtDate(r.dueDate) },
    { key: 'total', header: 'Importe', align: 'end', width: '8rem', cell: (r) => fmtMoney(r.total, r.currency) },
    {
      key: 'status', header: 'Estado', filter: 'select', width: '9rem',
      value: (r) => STATUS_LABEL[r.status],
      cell: (r) => <Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge>,
    },
  ];

  const subColumns: Array<DataTableColumn<CloudSubscription>> = [
    { key: 'planName', header: 'Suscripción', width: 'minmax(12rem,1.5fr)' },
    { key: 'planPrice', header: 'Precio', align: 'end', width: '9rem', cell: (r) => `${fmtMoney(r.planPrice, 'EUR')}/${r.billingCycle || 'mes'}` },
    { key: 'currentPeriodEnd', header: 'Renueva', filter: 'dateRange', width: '9rem', cell: (r) => fmtDate(r.currentPeriodEnd ?? '') },
    {
      key: 'status', header: 'Estado', filter: 'select', width: '9rem',
      value: (r) => STATUS_LABEL[r.status],
      cell: (r) => <Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge>,
    },
  ];

  return (
    <PageScaffold title="Billing" footer={<PageTabBar value={tab} items={tabs} onChange={setTab} />}>
      <div className="flex h-full flex-col">
        {tab === 'invoices' && (
          <DataTable
            columns={invoiceColumns}
            rows={invoices}
            rowKey={(r) => String(r.id)}
            title="Facturas"
            loading={loadingInvoices}
            pageSize={12}
            enableExport
            exportFilename="facturas"
            emptyMessage="No hay facturas"
            rowActions={(r) => (
              <IonButton fill="clear" size="small" aria-label={`Descargar ${r.number}`} onClick={() => downloadInvoice(r.id)}>
                <LuDownload size={17} />
              </IonButton>
            )}
            cardIcon={() => <LuFileText size={18} />}
            cardTitle={(r) => r.number}
            renderCard={(r) => (
              <div className="flex flex-col gap-2 p-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{fmtMoney(r.total, r.currency)}</span>
                  <Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                </div>
                <span className="text-xs text-[color:var(--ion-color-medium)]">Emitida {fmtDate(r.issueDate)} · Vence {fmtDate(r.dueDate)}</span>
              </div>
            )}
          />
        )}

        {tab === 'subscriptions' && (
          <DataTable
            columns={subColumns}
            rows={subscriptions}
            rowKey={(r) => String(r.id)}
            title="Suscripciones"
            loading={loadingSubs}
            emptyMessage="No hay suscripciones activas"
            cardIcon={() => <LuCreditCard size={18} />}
            cardTitle={(r) => r.planName}
            renderCard={(r) => (
              <div className="flex flex-col gap-2 p-4">
                <span className="font-semibold">{fmtMoney(r.planPrice, 'EUR')}/{r.billingCycle || 'mes'}</span>
                <Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                {r.currentPeriodEnd && (
                  <span className="text-xs text-[color:var(--ion-color-medium)]">
                    {r.cancelAtPeriodEnd ? 'Finaliza' : 'Renueva'} {fmtDate(r.currentPeriodEnd)}
                  </span>
                )}
              </div>
            )}
          />
        )}

        {tab === 'payments' && (
          <div className="grid flex-1 place-items-center text-center text-[color:var(--ion-color-medium)]">
            La gestión del método de pago se realiza desde el portal de facturación.
          </div>
        )}
      </div>
    </PageScaffold>
  );
}

// Descarga del PDF de la factura (endpoint real del Cloud).
async function downloadInvoice(id: number) {
  const token = getAccessToken();
  try {
    const res = await fetch(`${config.cloudApiUrl}/api/v1/billing/invoices/${id}/download/`, {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'X-Client-Type': 'hub' },
    });
    if (!res.ok) throw new Error(String(res.status));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `factura-${id}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('No se pudo descargar la factura', e);
  }
}

export default BillingPage;
