import { useEffect, useRef } from 'react';
import { Icon } from './Icon';

export interface SearchbarProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  kbd?: string;
}

export function Searchbar({ value, onChange, placeholder = 'Buscar…', kbd = '⌘K' }: SearchbarProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    function h(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        ref.current?.focus();
      }
    }
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  return (
    <div className="ctl relative flex h-11 items-center gap-2.5 rounded-[var(--r-ctl)] pl-3 pr-2 transition focus-within:border-[var(--brand)]">
      <Icon name="search" size={18} style={{ color: 'var(--muted)' }} />
      <input
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-full w-full bg-transparent text-[14px] outline-none placeholder:text-[var(--faint)]"
        style={{ color: 'var(--ink)' }}
      />
      {value ? (
        <button aria-label="Limpiar" onClick={() => onChange('')} className="grid h-6 w-6 place-items-center rounded-md text-[var(--muted)] hover:bg-[var(--surface-2)]">
          <Icon name="x" size={15} />
        </button>
      ) : kbd ? (
        <span className="kbd hidden sm:inline">{kbd}</span>
      ) : null}
    </div>
  );
}
