// Teclado numérico de PIN (4 dígitos por defecto) con indicadores visuales.
// Reutilizable para login PIN y setup PIN. ARQUITECTURA.md §2.9.
import { cx } from './lib/cx';
import { Icon } from './Icon';

export interface PinPadProps {
  value: string;
  onChange: (next: string) => void;
  length?: number;
  error?: boolean;
  disabled?: boolean;
}

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];

export function PinPad({ value, onChange, length = 4, error, disabled }: PinPadProps) {
  function push(d: string) {
    if (disabled) return;
    if (value.length >= length) return;
    onChange((value + d).slice(0, length));
  }
  function back() {
    if (disabled) return;
    onChange(value.slice(0, -1));
  }

  return (
    <div className="flex flex-col items-center gap-6">
      {/* indicadores */}
      <div className={cx('flex gap-3', error && 'shake')}>
        {Array.from({ length }).map((_, i) => {
          const filled = i < value.length;
          return (
            <span
              key={i}
              className="h-3.5 w-3.5 rounded-full transition"
              style={{
                background: error ? 'var(--bad-ink)' : filled ? 'var(--brand)' : 'transparent',
                border: '2px solid ' + (error ? 'var(--bad-ink)' : filled ? 'var(--brand)' : 'color-mix(in srgb,var(--ink) 25%,var(--line))'),
              }}
            />
          );
        })}
      </div>

      {/* teclado */}
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((k) => (
          <PadKey key={k} onClick={() => push(k)} disabled={disabled}>{k}</PadKey>
        ))}
        <span />
        <PadKey onClick={() => push('0')} disabled={disabled}>0</PadKey>
        <PadKey onClick={back} disabled={disabled} aria-label="Borrar">
          <Icon name="delete" size={22} />
        </PadKey>
      </div>
    </div>
  );
}

function PadKey({ children, onClick, disabled, ...rest }: { children: React.ReactNode; onClick: () => void; disabled?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="ring-focus grid h-16 w-16 place-items-center rounded-[18px] font-display text-[24px] font-semibold transition active:scale-95 disabled:opacity-40"
      style={{ background: 'var(--surface)', color: 'var(--ink)', border: '1px solid var(--line)' }}
      {...rest}
    >
      {children}
    </button>
  );
}
