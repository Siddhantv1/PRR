import { ArrowLeft, Circle, Terminal } from 'lucide-react'

import { DiffViewer } from './DiffViewer'
import { PipelineProgress } from './PipelineProgress'
import { PRPreview } from './PRPreview'
import { ReviewTranscript } from './ReviewTranscript'
import { StreamingFeed } from './StreamingFeed'
import { useRunStream } from '../hooks/useRunStream'

export function RunDetail({ runId, onBack }) {
  const {
    stages,
    streamEvents,
    reviewComments,
    result,
    error,
    connected,
    revisionRound,
  } = useRunStream(runId)

  return (
    <main className="run-shell">
      <header className="run-header">
        <button type="button" className="icon-button" onClick={onBack} aria-label="Back">
          <ArrowLeft size={18} />
        </button>
        <div>
          <p className="eyebrow">Run</p>
          <h1>{runId}</h1>
        </div>
        <div className={`connection ${connected ? 'connected' : ''}`}>
          <Circle size={10} fill="currentColor" />
          <span>{connected ? 'Live' : 'Offline'}</span>
        </div>
      </header>

      <PipelineProgress stages={stages} revisionRound={revisionRound} />

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="run-grid">
        <div className="panel event-panel">
          <div className="panel-heading">
            <Terminal size={16} />
            <h2>Live Stream</h2>
          </div>
          <StreamingFeed events={streamEvents} />
        </div>

        <ReviewTranscript
          reviewComments={reviewComments}
          revisionRounds={result?.review_rounds || revisionRound}
        />
      </section>

      {result ? (
        <section className="result-stack">
          <DiffViewer diff={result.diff} />
          <PRPreview title={result.pr_title} body={result.pr_body} />
        </section>
      ) : null}
    </main>
  )
}
