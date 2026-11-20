import { Loader2, Send } from 'lucide-react'
import { useState } from 'react'

import { HomeSections } from './HomeSections'
import { PipelineGlyph } from './PipelineGlyph'

const ISSUE_URL_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+$/

export function IssueInput({ onRunCreated }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    const issueUrl = url.trim()
    if (!ISSUE_URL_RE.test(issueUrl)) {
      setError('Enter a GitHub issue URL like https://github.com/spf13/cobra/issues/123')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_url: issueUrl }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Could not start the run.')
      }
      onRunCreated(data.run_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="home">
      <header className="topbar">
        <div className="container topbar__inner">
          <span className="wordmark">prr</span>
          <nav className="topbar__nav" aria-label="Sections">
            <a href="#what">What it is</a>
            <a href="#how">How it works</a>
            <a href="#limits">Before you run it</a>
          </nav>
        </div>
      </header>
      <main>
        <section className="home__main home__grid container" aria-label="Run the agent">
        <form className="issue-form" onSubmit={handleSubmit}>
          <h1>Pre-Reviewed Contributor</h1>
          <p className="subtitle">
            Paste a GitHub issue URL. The agent will fix it, then review its own work.
          </p>
          <div className="issue-field">
            <label className="input-label" htmlFor="issue-url">
              Issue URL
            </label>
            <div className="issue-field__row">
              <input
                id="issue-url"
                type="url"
                inputMode="url"
                autoComplete="off"
                value={url}
                placeholder="https://github.com/spf13/cobra/issues/…"
                onChange={(event) => setUrl(event.target.value)}
                spellCheck="false"
                aria-invalid={error ? 'true' : undefined}
                aria-describedby="issue-url-help"
              />
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading}
                aria-busy={loading ? 'true' : undefined}
              >
                {loading ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
                {loading ? 'Starting' : 'Run Agent'}
              </button>
            </div>
            <p className="error-text" id="issue-url-help" aria-live="polite">
              {error}
            </p>
          </div>
        </form>
        <PipelineGlyph />
        </section>
        <HomeSections />
      </main>
    </div>
  )
}
