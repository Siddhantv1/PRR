import { Check, X } from 'lucide-react'

const STAGE_LABELS = [
  ['dna_extractor', 'DNA Extractor'],
  ['issue_analyst', 'Issue Analyst'],
  ['contributor', 'Contributor'],
  ['maintainer', 'Maintainer'],
  ['output_generator', 'Output'],
]

function StatusIndicator({ status }) {
  if (status === 'complete') {
    return (
      <span className="stage-icon complete" aria-label="complete">
        <Check size={14} />
      </span>
    )
  }

  if (status === 'error') {
    return (
      <span className="stage-icon error" aria-label="error">
        <X size={14} />
      </span>
    )
  }

  return <span className={`stage-dot ${status}`} aria-label={status} />
}

export function PipelineProgress({ stages, revisionRound = 0, maxRevisionRounds = 3 }) {
  return (
    <section className="progress-panel" aria-label="Pipeline progress">
      <div className="stage-row">
        {STAGE_LABELS.map(([key, label], index) => {
          const status = stages[key] || 'pending'
          const stageLabel = status === 'running' ? `${label} ...` : label
          const separator = key === 'contributor' ? '⇄' : '→'
          return (
            <div className="stage-wrap" key={key}>
              <div className={`stage-pill ${status}`}>
                <StatusIndicator status={status} />
                <span>{stageLabel}</span>
              </div>
              {index < STAGE_LABELS.length - 1 ? (
                <span className="stage-separator" aria-hidden="true">
                  {separator}
                </span>
              ) : null}
            </div>
          )
        })}
      </div>
      {revisionRound > 0 ? (
        <p className="revision-counter">
          Revision round {revisionRound} / {maxRevisionRounds}
        </p>
      ) : null}
    </section>
  )
}
