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
    maxRevisionRounds,
    startedAt,
    currentDescription,
    lastActivity,
  } = useRunStream(runId)

  return (
    <div className="run">
      <header className="topbar run-header">
        <div className="container topbar__inner">
          <button type="button" className="icon-button" onClick={onBack} aria-label="Back">
            <ArrowLeft size={18} />
          </button>
          <span className="wordmark">prr</span>
          <h1>{runId}</h1>
          <div className={`connection ${connected ? 'connected' : ''}`} role="status">
            <Circle size={8} fill="currentColor" aria-hidden="true" />
            <span>{connected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </header>

      <main className="run-shell container">
        <PipelineProgress
          stages={stages}
          revisionRound={revisionRound}
          maxRevisionRounds={maxRevisionRounds}
          startedAt={startedAt}
          currentDescription={currentDescription}
          lastActivity={lastActivity}
          hasResult={Boolean(result)}
          hasError={Boolean(error)}
        />

        {error ? (
          <div className="error-banner" role="alert">
            {error}
          </div>
        ) : null}

        {result ? (
          <section className="result-stack">
            <DiffViewer diff={result.diff} />
            <PRPreview title={result.pr_title} body={result.pr_body} />
          </section>
        ) : null}

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
      </main>
    </div>
  )
}
