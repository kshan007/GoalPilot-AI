import type { ChangeEvent, ReactNode } from 'react'

/* --------------------------------------------------------------- surfaces */

export function Card({
  title,
  description,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <section className={`gp-card p-4 sm:p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

/* ---------------------------------------------------------------- buttons */

type ButtonTone = 'primary' | 'secondary' | 'danger' | 'ghost'

const TONES: Record<ButtonTone, string> = {
  primary: 'bg-accent-600 text-white hover:bg-accent-700 disabled:bg-accent-300',
  secondary:
    'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
  ghost: 'text-accent-700 hover:bg-accent-50 disabled:text-slate-400',
}

export function Button({
  children,
  onClick,
  type = 'button',
  tone = 'primary',
  disabled = false,
  pending = false,
  className = '',
  size = 'md',
}: {
  children: ReactNode
  onClick?: () => void
  type?: 'button' | 'submit'
  tone?: ButtonTone
  disabled?: boolean
  pending?: boolean
  className?: string
  size?: 'sm' | 'md'
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || pending}
      className={`inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed ${
        size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm'
      } ${TONES[tone]} ${className}`}
    >
      {pending ? 'Working...' : children}
    </button>
  )
}

export function LinkButton({
  children,
  href,
  tone = 'secondary',
  className = '',
}: {
  children: ReactNode
  href: string
  tone?: ButtonTone
  className?: string
}) {
  return (
    <a
      href={href}
      className={`inline-flex items-center justify-center rounded-md px-3.5 py-2 text-sm font-medium ${
        tone === 'primary' ? 'bg-accent-600 text-white hover:bg-accent-700' : TONES[tone]
      } ${className}`}
    >
      {children}
    </a>
  )
}

/* ----------------------------------------------------------------- fields */

export function Field({
  label,
  hint,
  children,
  className = '',
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <label className={`block ${className}`}>
      <span className="gp-label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export function TextInput({
  value,
  onChange,
  type = 'text',
  placeholder,
  disabled,
  min,
  max,
  step,
  id,
}: {
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
  disabled?: boolean
  min?: number
  max?: number
  step?: number
  id?: string
}) {
  return (
    <input
      id={id}
      className="gp-input"
      type={type}
      value={value}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
    />
  )
}

export function SelectInput({
  value,
  onChange,
  options,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  disabled?: boolean
}) {
  return (
    <select
      className="gp-input"
      value={value}
      disabled={disabled}
      onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function Checkbox({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  hint?: ReactNode
  disabled?: boolean
}) {
  return (
    <label className="flex items-start gap-2 text-sm text-slate-700">
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-accent-600 focus:ring-accent-500"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        {label}
        {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  )
}

/* ---------------------------------------------------- explicit four states */

export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-md border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500"
    >
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-accent-600" />
      {label}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-4">
      <p className="text-sm font-semibold text-red-800">Something went wrong</p>
      <p className="mt-1 text-sm text-red-700">{message}</p>
      {onRetry && (
        <div className="mt-3">
          <Button tone="secondary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string
  message: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6">
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function InlineNotice({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'warning' | 'success' | 'error'
  children: ReactNode
}) {
  const tones = {
    info: 'border-slate-200 bg-slate-50 text-slate-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    error: 'border-red-200 bg-red-50 text-red-700',
  }
  return <div className={`rounded-md border px-3 py-2 text-sm ${tones[tone]}`}>{children}</div>
}

/* ------------------------------------------------------------------ atoms */

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'positive' | 'negative' | 'warning' | 'accent'
}) {
  const tones = {
    neutral: 'bg-slate-100 text-slate-700',
    positive: 'bg-emerald-100 text-emerald-800',
    negative: 'bg-red-100 text-red-700',
    warning: 'bg-amber-100 text-amber-800',
    accent: 'bg-accent-100 text-accent-800',
  }
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

/**
 * Provenance label. The API distinguishes actual / estimated / projected; the UI repeats it
 * on every value whose provenance is not "recorded fact".
 */
export function Provenance({ kind }: { kind: 'actual' | 'estimated' | 'projected' | 'historical' }) {
  const tone = kind === 'actual' ? 'positive' : kind === 'estimated' ? 'warning' : 'accent'
  // The badge means "where did this number come from". Say that in words a user knows, not in
  // accounting vocabulary the rest of the product never uses.
  const label =
    kind === 'actual'
      ? 'recorded'
      : kind === 'estimated'
        ? 'forecast'
        : kind === 'projected'
          ? 'planned'
          : 'past'
  return <Badge tone={tone}>{label}</Badge>
}

export function StatCard({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'positive' | 'negative' | 'warning' | 'accent'
}) {
  const accents = {
    neutral: 'text-slate-900',
    positive: 'text-emerald-700',
    negative: 'text-red-700',
    warning: 'text-amber-700',
    accent: 'text-accent-700',
  }
  return (
    <div className="gp-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 font-mono text-lg font-semibold tabular-nums ${accents[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

export function KeyValueTable({ rows }: { rows: Array<{ key: string; value: ReactNode }> }) {
  return (
    <dl className="divide-y divide-slate-100">
      {rows.map((row) => (
        <div key={row.key} className="flex flex-col gap-1 py-2 sm:flex-row sm:justify-between">
          <dt className="text-sm text-slate-500">{row.key}</dt>
          <dd className="text-sm font-medium text-slate-800 sm:text-right">{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function WarningList({ warnings }: { warnings: string[] }) {
  if (!warnings || warnings.length === 0) return null
  return (
    <ul className="space-y-1">
      {warnings.map((warning) => (
        <li key={warning} className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {warning}
        </li>
      ))}
    </ul>
  )
}

export function JsonBlock({ value, label }: { value: unknown; label?: string }) {
  const rows = flatten(value)
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500">No {label ?? 'data'} was returned by the API.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="gp-table">
        <tbody>
          {rows.map((row) => (
            <tr key={row.path}>
              <td className="w-1/2 text-slate-500">{row.path}</td>
              <td className="font-mono text-xs text-slate-800">{row.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface FlatRow {
  path: string
  text: string
}

/** Flatten an arbitrary API dictionary into dotted key/value rows for display. */
export function flatten(value: unknown, prefix = ''): FlatRow[] {
  if (value === null || value === undefined) return [{ path: prefix || 'value', text: '--' }]
  if (typeof value === 'number') {
    const text = Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
    return [{ path: prefix || 'value', text }]
  }
  if (typeof value === 'boolean' || typeof value === 'string') {
    return [{ path: prefix || 'value', text: String(value) }]
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return [{ path: prefix || 'items', text: '(none)' }]
    return value.flatMap((item, index) =>
      flatten(item, `${prefix ? `${prefix}.` : ''}${index}`),
    )
  }
  const entries = Object.entries(value as Record<string, unknown>)
  if (entries.length === 0) return [{ path: prefix || 'object', text: '(empty)' }]
  return entries.flatMap(([key, item]) => flatten(item, prefix ? `${prefix}.${key}` : key))
}
