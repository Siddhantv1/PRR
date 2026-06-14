import { useEffect, useMemo, useState } from 'react'
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

function formatElapsed(startedAt, now) {
  if (!startedAt) {
    return '0s'
  }
  const seconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000))
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

function calculateProgress(stages, hasResult) {
  if (hasResult) {
    return 100
  }
  const stageValues = STAGE_LABELS.map(([key]) => stages[key] || 'pending')
  const complete = stageValues.filter((status) => status === 'complete').length
  const running = stageValues.some((status) => status === 'running') ? 0.55 : 0
  return Math.min(99, Math.round(((complete + running) / STAGE_LABELS.length) * 100))
}

function getActiveStage(stages) {
  return STAGE_LABELS.find(([key]) => stages[key] === 'running')?.[0] || null
}

export function PipelineProgress({
  stages,
  revisionRound = 0,
  maxRevisionRounds = 2,
  currentDescription = 'Preparing run',
  lastActivity = 'Waiting for agent...',
  startedAt,
  hasResult = false,
  hasError = false,
}) {
  const [now, setNow] = useState(() => Date.now())
  const progress = useMemo(
    () => calculateProgress(stages, hasResult),
    [stages, hasResult],
  )
  const activeStage = getActiveStage(stages)

  useEffect(() => {
    if (hasResult || hasError) {
      return undefined
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [hasResult, hasError])

  return (
    <section className="progress-panel" aria-label="Pipeline progress">
      <div className="progress-summary">
        <div>
          <p className="eyebrow">Current step</p>
          <h2>{currentDescription}</h2>
        </div>
        <div className="progress-stats">
          <span>{progress}%</span>
          <span>{formatElapsed(startedAt, now)}</span>
        </div>
      </div>
      <div
        className={`progress-track ${hasResult ? 'complete' : ''} ${hasError ? 'error' : ''}`}
        aria-label={`Run progress ${progress}%`}
      >
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="activity-strip" aria-live="polite">
        <span className={`activity-pulse ${hasError ? 'error' : ''}`} />
        <span>{lastActivity}</span>
      </div>
      <div className="stage-row">
        {STAGE_LABELS.map(([key, label], index) => {
          const status = stages[key] || 'pending'
          const stageLabel = status === 'running' ? `${label} ...` : label
          const separator = key === 'contributor' ? '⇄' : '→'
          return (
            <div className="stage-wrap" key={key}>
              <div className={`stage-pill ${status} ${activeStage === key ? 'active' : ''}`}>
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
