// Marca ERPlora (100% CSS, de logo.css): hub central + 8 módulos.
import { cx } from './lib/cx';

type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export function LogoMark({ size = 'sm', mono = false }: { size?: Size; mono?: boolean }) {
  return (
    <span className={cx('erp-logo', size, mono && 'mono')} aria-hidden>
      <i className="erp-nw" /><i className="erp-n" /><i className="erp-ne" />
      <i className="erp-w" /><i className="erp-hub" /><i className="erp-e" />
      <i className="erp-sw" /><i className="erp-s" /><i className="erp-se" />
    </span>
  );
}

export function Logo({ size = 'sm', wordmark = true }: { size?: Size; wordmark?: boolean }) {
  return (
    <span className={cx('erp-lockup', size, 'flex items-center gap-2.5')}>
      <LogoMark size={size} />
      {wordmark && <span className="erp-wordmark font-display" style={{ color: 'var(--ink)' }}>erplora</span>}
    </span>
  );
}
