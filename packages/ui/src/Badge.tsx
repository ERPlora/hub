import type { ReactNode } from 'react';

type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'purple' | 'teal' | 'neutral';

const TONE: Record<Tone, { bg: string; ink: string }> = {
  ok: { bg: 'var(--ok-bg)', ink: 'var(--ok-ink)' },
  warn: { bg: 'var(--warn-bg)', ink: 'var(--warn-ink)' },
  bad: { bg: 'var(--bad-bg)', ink: 'var(--bad-ink)' },
  info: { bg: 'var(--info-bg)', ink: 'var(--info-ink)' },
  purple: { bg: 'var(--purple-bg)', ink: 'var(--purple-ink)' },
  teal: { bg: 'var(--teal-bg)', ink: 'var(--teal-ink)' },
  neutral: { bg: 'var(--surface-2)', ink: 'var(--muted)' },
};

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  const t = TONE[tone];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-[var(--r-pill)] px-2.5 py-0.5 text-[12px] font-semibold"
      style={{ background: t.bg, color: t.ink }}
    >
      {children}
    </span>
  );
}
