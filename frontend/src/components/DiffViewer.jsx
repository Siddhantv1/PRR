import { useMemo, useState } from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { Copy, CopyCheck } from 'lucide-react'

function parseDiff(diff) {
  const oldLines = []
  const newLines = []
  let additions = 0
  let deletions = 0

  for (const line of diff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('index ')) {
      continue
    }

    if (line.startsWith('diff --git') || line.startsWith('@@')) {
      oldLines.push(line)
      newLines.push(line)
      continue
    }

    if (line.startsWith('+')) {
      additions += 1
      newLines.push(line.slice(1))
      continue
    }

    if (line.startsWith('-')) {
      deletions += 1
      oldLines.push(line.slice(1))
      continue
    }

    const content = line.startsWith(' ') ? line.slice(1) : line
    oldLines.push(content)
    newLines.push(content)
  }

  return {
    oldValue: oldLines.join('\n'),
    newValue: newLines.join('\n'),
    additions,
    deletions,
  }
}

export function DiffViewer({ diff }) {
  const [copied, setCopied] = useState(false)
  const normalizedDiff = diff || ''
  const parsed = useMemo(() => parseDiff(normalizedDiff), [normalizedDiff])

  async function copyDiff() {
    await navigator.clipboard.writeText(normalizedDiff)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  if (!normalizedDiff.trim() || normalizedDiff.trim() === 'No changes.') {
    return (
      <section className="panel output-panel">
        <div className="output-header">
          <h2>Diff</h2>
        </div>
        <p className="muted">No changes detected.</p>
      </section>
    )
  }

  return (
    <section className="panel output-panel">
      <div className="output-header">
        <div>
          <h2>Diff</h2>
          <p>
            +{parsed.additions} lines / -{parsed.deletions} lines
          </p>
        </div>
        <button type="button" className="copy-button" onClick={copyDiff}>
          {copied ? <CopyCheck size={15} /> : <Copy size={15} />}
          {copied ? 'Copied' : 'Copy diff'}
        </button>
      </div>
      <div className="diff-wrap">
        <ReactDiffViewer
          oldValue={parsed.oldValue}
          newValue={parsed.newValue}
          splitView={false}
          useDarkTheme
          hideLineNumbers={false}
        />
      </div>
    </section>
  )
}
