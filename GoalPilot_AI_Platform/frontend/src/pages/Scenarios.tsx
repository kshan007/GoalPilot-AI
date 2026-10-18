import { useState } from 'react'
import { errorMessage, scenariosApi } from '../api/client'
import type { Algorithm, ScenarioRun } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatDateTime, valueText } from '../lib/format'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  JsonBlock,
  LoadingState,
  PageHeader,
  SelectInput,
  TextInput,
} from '../components/ui'

interface ParameterRow {
  key: string
  value: string
}

export default function Scenarios() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([scenariosApi.presets(), scenariosApi.runs()]),
    [],
  )

  const [preset, setPreset] = useState('')
  const [algorithm, setAlgorithm] = useState<Algorithm>('lp')
  const [name, setName] = useState('')
  const [rows, setRows] = useState<ParameterRow[]>([{ key: '', value: '' }])
  const [result, setResult] = useState<ScenarioRun | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [history, setHistory] = useState<ScenarioRun | null>(null)

  if (loading) return <LoadingState label="Loading scenario presets..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const presets = data ? data[0] : []
  const runs = data ? data[1] : { limit: 0, items: [] }

  return (
    <div className="space-y-6">
      <PageHeader
        title="What if…?"
        description="Try a change — prices rising faster, lower investment returns — and see how your plan holds up. It runs your plan twice, once normally and once under the change, so you can see what that one change costs you. Nothing here alters your real plan."
      />

      <Card title="Types of change" description="Every preset declares the parameters it changes and the assumption it rests on.">
        {presets.length === 0 ? (
          <EmptyState
            title="No scenario presets"
            message="The API returned no preset, so no scenario can be configured."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Preset</th>
                  <th>Name</th>
                  <th>Description</th>
                  <th>Default parameters</th>
                  <th>Assumption note</th>
                </tr>
              </thead>
              <tbody>
                {presets.map((item) => (
                  <tr key={item.preset}>
                    <td className="font-mono text-xs">{item.preset}</td>
                    <td>{item.name}</td>
                    <td className="text-sm text-slate-600">{item.description}</td>
                    <td className="font-mono text-xs">{valueText(item.parameters)}</td>
                    <td className="text-xs text-slate-500">{item.assumption_note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Run a scenario">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Preset">
            <SelectInput
              value={preset || (presets[0]?.preset ?? '')}
              onChange={setPreset}
              options={presets.map((item) => ({ value: item.preset, label: item.name }))}
              disabled={pending || presets.length === 0}
            />
          </Field>
          <Field label="Algorithm" hint="The same algorithm solves both cases.">
            <SelectInput
              value={algorithm}
              onChange={(value) => setAlgorithm(value as Algorithm)}
              options={[
                { value: 'lp', label: 'lp' },
                { value: 'rl', label: 'rl' },
                { value: 'hybrid', label: 'hybrid' },
              ]}
              disabled={pending}
            />
          </Field>
          <Field label="Name" hint="Optional label for this run.">
            <TextInput value={name} onChange={setName} disabled={pending} />
          </Field>
        </div>

        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-slate-700">Parameter overrides</p>
          <div className="space-y-2">
            {rows.map((row, index) => (
              <div key={index} className="flex gap-2">
                <TextInput
                  value={row.key}
                  onChange={(value) =>
                    setRows((current) =>
                      current.map((item, position) => (position === index ? { ...item, key: value } : item)),
                    )
                  }
                  placeholder="parameter name"
                  disabled={pending}
                />
                <TextInput
                  type="number"
                  value={row.value}
                  onChange={(value) =>
                    setRows((current) =>
                      current.map((item, position) => (position === index ? { ...item, value } : item)),
                    )
                  }
                  placeholder="value"
                  disabled={pending}
                />
              </div>
            ))}
          </div>
          <Button
            tone="secondary"
            size="sm"
            className="mt-2"
            disabled={pending}
            onClick={() => setRows((current) => [...current, { key: '', value: '' }])}
          >
            Add parameter
          </Button>
        </div>

        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}

        <div className="mt-5">
          <Button
            pending={pending}
            onClick={async () => {
              setPending(true)
              setActionError(null)
              try {
                const parameters: Record<string, number> = {}
                for (const row of rows) {
                  if (row.key.trim() && row.value !== '') parameters[row.key.trim()] = Number(row.value)
                }
                const response = await scenariosApi.run({
                  preset: preset || presets[0]?.preset || '',
                  parameters,
                  algorithm,
                  name,
                })
                setResult(response)
              } catch (caught) {
                setActionError(errorMessage(caught))
              } finally {
                setPending(false)
              }
            }}
          >
            Run scenario
          </Button>
        </div>
      </Card>

      {result && (
        <Card
          title={`Result of ${result.name ?? result.preset ?? 'the scenario'}`}
          description={`Preset ${result.preset ?? '--'}, parameters ${valueText(result.parameters)}`}
        >
          <div className="grid gap-6 xl:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Baseline</p>
              <JsonBlock value={result.baseline} label="baseline" />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Stressed</p>
              <JsonBlock value={result.stressed} label="stressed" />
            </div>
          </div>
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium text-slate-700">Deltas</p>
            <JsonBlock value={result.deltas} label="deltas" />
          </div>
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium text-slate-700">Narrative</p>
            {result.narrative.length === 0 ? (
              <EmptyState title="No narrative" message="The scenario returned no narrative lines." />
            ) : (
              <ul className="space-y-2 text-sm text-slate-700">
                {result.narrative.map((line) => (
                  <li key={line} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                    {line}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      )}

      <Card title={`Scenario history (${runs.items.length})`}>
        {runs.items.length === 0 ? (
          <EmptyState
            title="No scenario runs yet"
            message="Run a scenario above to build a history. Each run stores its baseline and stressed plan."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Preset</th>
                  <th>Baseline run</th>
                  <th>Stressed run</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.items.map((run) => (
                  <tr key={run.id}>
                    <td>#{run.id}</td>
                    <td>{run.preset ?? '--'}</td>
                    <td>{run.baseline_run_id === null ? '--' : `#${run.baseline_run_id}`}</td>
                    <td>{run.stressed_run_id === null ? '--' : `#${run.stressed_run_id}`}</td>
                    <td>{formatDateTime(run.created_at)}</td>
                    <td>
                      <Button
                        tone="secondary"
                        size="sm"
                        disabled={pending}
                        onClick={async () => {
                          setPending(true)
                          setActionError(null)
                          try {
                            setHistory(await scenariosApi.run1(run.id))
                          } catch (caught) {
                            setActionError(errorMessage(caught))
                          } finally {
                            setPending(false)
                          }
                        }}
                      >
                        View
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}

        {history && (
          <div className="mt-5 space-y-3">
            <InlineNotice tone="info">
              Showing stored scenario run #{history.id}
              {history.name ? ` (${history.name})` : ''}.
            </InlineNotice>
            <JsonBlock value={history.deltas} label="deltas" />
          </div>
        )}
      </Card>
    </div>
  )
}

