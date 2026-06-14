import { HelpCircle, Lightbulb, ShieldCheck, XOctagon } from 'lucide-react'

const COMMENT_META = {
  BLOCKING: { icon: XOctagon, label: 'BLOCKING' },
  SUGGESTION: { icon: Lightbulb, label: 'SUGGESTION' },
  QUESTION: { icon: HelpCircle, label: 'QUESTION' },
  APPROVED: { icon: ShieldCheck, label: 'APPROVED' },
}

function normalizeComment(comment) {
  return {
    round: comment.round ?? comment.round_number ?? 1,
    kind: (comment.kind ?? comment.comment_type ?? 'QUESTION').toUpperCase(),
    text: comment.text ?? comment.content ?? '',
  }
}

export function ReviewTranscript({ reviewComments, revisionRounds = 0 }) {
  const comments = reviewComments.map(normalizeComment)
  const approved = comments.some((comment) => comment.kind === 'APPROVED')
  const totalRounds =
    revisionRounds || Math.max(0, ...comments.map((comment) => Number(comment.round) || 0))

  const rounds = comments.reduce((grouped, comment) => {
    const round = comment.round || 1
    grouped[round] ||= []
    grouped[round].push(comment)
    return grouped
  }, {})

  return (
    <section className="panel review-transcript">
      <div className="transcript-header">
        <h2>Review Transcript</h2>
        <p>
          {totalRounds} revision round(s) · {comments.length} total comments ·{' '}
          {approved ? 'Approved' : 'Pending'}
        </p>
      </div>

      {approved ? (
        <div className="approved-banner">
          <ShieldCheck size={18} />
          <span>✓ Maintainer Approved</span>
        </div>
      ) : null}

      {comments.length === 0 ? (
        <p className="muted">Waiting for maintainer review...</p>
      ) : (
        <div className="round-list">
          {Object.entries(rounds)
            .sort(([left], [right]) => Number(left) - Number(right))
            .map(([round, roundComments]) => (
              <section className="round-section" key={round}>
                <h3>Round {round}</h3>
                <div className="round-comments">
                  {roundComments.map((comment, index) => {
                    const meta = COMMENT_META[comment.kind] || COMMENT_META.QUESTION
                    const Icon = meta.icon
                    return (
                      <article
                        className={`transcript-comment ${comment.kind.toLowerCase()}`}
                        key={`${round}-${comment.kind}-${index}`}
                      >
                        <div className="transcript-tag">
                          <Icon size={16} />
                          <span>[{meta.label}]</span>
                        </div>
                        <p>{comment.text}</p>
                      </article>
                    )
                  })}
                </div>
              </section>
            ))}
        </div>
      )}
    </section>
  )
}
