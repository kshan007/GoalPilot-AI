import type { ReactNode } from 'react'

/**
 * A plain-language explainer that stays out of the way until asked.
 *
 * Used wherever a screen would otherwise need jargon to explain itself: the question is written
 * the way a person would ask it, and the answer avoids model, solver and accounting vocabulary.
 */
export function Explain({ question, children }: { question: string; children: ReactNode }) {
  return (
    <details className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
      <summary className="cursor-pointer select-none font-medium text-slate-800">
        {question}
      </summary>
      <div className="mt-2 space-y-2 leading-relaxed text-slate-600">{children}</div>
    </details>
  )
}
