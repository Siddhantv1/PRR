import { useEffect, useRef, useState } from 'react'
import { CheckCircle, MessageSquare, Wrench, XCircle } from 'lucide-react'

function stringifyArgs(args) {
  try {
    return JSON.stringify(args || {}, null, 2)
  } catch {
    return String(args)
  }
}

function relativeTime(value) {
  if (!value) {
    return 'now'
  }

  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 5) {
    return 'now'
  }
  if (seconds < 60) {
    return `${seconds}s ago`
  }

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }

  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

function ToolCallEvent({ event, eventKey }) {
  const [expanded, setExpanded] = useState(false)
  const argsText = stringifyArgs(event.args)
  const visibleText = expanded || argsText.length <= 100 ? argsText : `${argsText.slice(0, 100)}...`

  return (
    <article className="stream-event tool-call">
      <Wrench size={16} className="stream-icon" />
      <div className="stream-content">
        <div className="stream-meta">
          <strong>{event.tool}</strong>
          <time>{relativeTime(event.receivedAt)}</time>
        </div>
        <button
          type="button"
          className="stream-collapse"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
          aria-controls={`tool-args-${eventKey}`}
        >
          <pre id={`tool-args-${eventKey}`}>{visibleText}</pre>
        </button>
      </div>
    </article>
  )
}

function ToolResultEvent({ event }) {
  const ok = event.ok !== false
  const Icon = ok ? CheckCircle : XCircle

  return (
    <article className={`stream-event tool-result ${ok ? 'ok' : 'failed'}`}>
      <Icon size={16} className="stream-icon" />
      <div className="stream-content">
        <div className="stream-meta">
          <strong>
            {event.tool} {ok ? '✓' : '✗'}
          </strong>
          <time>{relativeTime(event.receivedAt)}</time>
        </div>
        <pre className="stream-summary">{event.summary}</pre>
      </div>
    </article>
  )
}

function AgentTextEvent({ event }) {
  return (
    <article className="stream-event agent-text">
      <MessageSquare size={16} className="stream-icon" />
      <div className="stream-content">
        <div className="stream-meta">
          <strong>Agent</strong>
          <time>{relativeTime(event.receivedAt)}</time>
        </div>
        <p>{event.text}</p>
      </div>
    </article>
  )
}

function ReviewCommentEvent({ event }) {
  const kind = event.kind || 'COMMENT'

  return (
    <article className={`stream-event review-stream ${kind.toLowerCase()}`}>
      <div className="stream-content full">
        <div className="stream-meta">
          <span className={`review-badge ${kind.toLowerCase()}`}>[{kind}]</span>
          <time>{relativeTime(event.receivedAt)}</time>
        </div>
        <p>{event.text}</p>
      </div>
    </article>
  )
}

function RevisionStartEvent({ event }) {
  return (
    <div className="revision-divider">
      <span>── Revision Round {event.round} of {event.total} ──</span>
    </div>
  )
}

function InfoEvent({ event }) {
  return <p className="stream-info">{event.message || event.text}</p>
}

function GenericEvent({ event }) {
  return (
    <article className="stream-event generic">
      <div className="stream-content full">
        <div className="stream-meta">
          <strong>{event.type}</strong>
          <time>{relativeTime(event.receivedAt)}</time>
        </div>
        <pre className="stream-summary">{JSON.stringify(event, null, 2)}</pre>
      </div>
    </article>
  )
}

function StreamEvent({ event, eventKey }) {
  if (event.type === 'tool_call') {
    return <ToolCallEvent event={event} eventKey={eventKey} />
  }
  if (event.type === 'tool_result') {
    return <ToolResultEvent event={event} />
  }
  if (event.type === 'agent_text') {
    return <AgentTextEvent event={event} />
  }
  if (event.type === 'review_comment') {
    return <ReviewCommentEvent event={event} />
  }
  if (event.type === 'revision_start') {
    return <RevisionStartEvent event={event} />
  }
  if (event.type === 'info' || event.type === 'stage_info') {
    return <InfoEvent event={event} />
  }
  return <GenericEvent event={event} />
}

export function StreamingFeed({ events }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events])

  if (!events.length) {
    return (
      <div className="streaming-feed empty">
        <p>Waiting for agent...</p>
        <div ref={bottomRef} />
      </div>
    )
  }

  return (
    <div className="streaming-feed">
      {events.map((event, index) => (
        <StreamEvent
          event={event}
          eventKey={`${index}-${event.receivedAt || 'event'}`}
          key={`${event.receivedAt || 'event'}-${index}`}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
