import { useEffect, useState } from 'react'

import { IssueInput } from './components/IssueInput'
import { RunDetail } from './components/RunDetail'

function parseRunIdFromHash() {
  const match = window.location.hash.match(/^#\/run\/([^/]+)$/)
  return match ? decodeURIComponent(match[1]) : null
}

function App() {
  const [currentRunId, setCurrentRunId] = useState(() => parseRunIdFromHash())

  useEffect(() => {
    function handleHashChange() {
      setCurrentRunId(parseRunIdFromHash())
    }

    if (!window.location.hash) {
      window.location.hash = '#/'
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  function handleRunCreated(runId) {
    window.location.hash = `#/run/${encodeURIComponent(runId)}`
    setCurrentRunId(runId)
  }

  function handleBack() {
    window.location.hash = '#/'
    setCurrentRunId(null)
  }

  if (!currentRunId) {
    return <IssueInput onRunCreated={handleRunCreated} />
  }

  return <RunDetail runId={currentRunId} onBack={handleBack} />
}

export default App
