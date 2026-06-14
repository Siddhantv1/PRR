import { FolderGit2, Loader2, Send } from 'lucide-react'
import { useState } from 'react'

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
    <main className="home-shell">
      <form className="issue-card" onSubmit={handleSubmit}>
        <div className="brand-mark" aria-hidden="true">
          <FolderGit2 size={22} />
        </div>
        <h1>Pre-Reviewed Contributor</h1>
        <p className="subtitle">
          Paste a GitHub issue URL. The agent will fix it, then review its own work.
        </p>
        <label className="input-label" htmlFor="issue-url">
          Issue URL
        </label>
        <input
          id="issue-url"
          type="url"
          value={url}
          placeholder="https://github.com/spf13/cobra/issues/..."
          onChange={(event) => setUrl(event.target.value)}
          spellCheck="false"
        />
        {error ? <p className="error-text">{error}</p> : null}
        <button type="submit" disabled={loading}>
          {loading ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
          {loading ? 'Starting' : 'Run Agent'}
        </button>
      </form>
    </main>
  )
}
