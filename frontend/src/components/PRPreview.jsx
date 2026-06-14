import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Copy, CopyCheck, GitPullRequestArrow } from 'lucide-react'

export function PRPreview({ title, body }) {
  const [copied, setCopied] = useState(false)

  async function copyDescription() {
    await navigator.clipboard.writeText(`${title}\n\n${body}`)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <section className="panel pr-preview">
      <div className="output-header">
        <div>
          <h2>Pull Request Preview</h2>
          <p>PR opening is intentionally manual</p>
        </div>
        <button type="button" className="copy-button" onClick={copyDescription}>
          {copied ? <CopyCheck size={15} /> : <Copy size={15} />}
          {copied ? 'Copied' : 'Copy PR description'}
        </button>
      </div>

      <div className="github-pr-title">{title}</div>
      <div className="github-pr-body markdown-body">
        <ReactMarkdown>{body}</ReactMarkdown>
      </div>
      <button type="button" className="faux-pr-button" disabled>
        <GitPullRequestArrow size={16} />
        Would open PR →
      </button>
    </section>
  )
}
