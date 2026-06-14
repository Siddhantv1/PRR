import { useEffect, useMemo, useReducer } from 'react'

const INITIAL_STAGES = {
  dna_extractor: 'pending',
  issue_analyst: 'pending',
  contributor: 'pending',
  maintainer: 'pending',
  output_generator: 'pending',
}

const STREAM_EVENT_TYPES = new Set([
  'agent_text',
  'tool_call',
  'tool_result',
  'info',
  'stage_info',
  'review_comment',
  'revision_start',
])

function initialState() {
  return {
    stages: INITIAL_STAGES,
    streamEvents: [],
    reviewComments: [],
    result: null,
    error: null,
    connected: false,
    revisionRound: 0,
  }
}

function appendEvent(events, event) {
  return [...events, { ...event, receivedAt: new Date().toISOString() }].slice(-200)
}

function markAllStages(status) {
  return Object.fromEntries(Object.keys(INITIAL_STAGES).map((stage) => [stage, status]))
}

function reducer(state, action) {
  if (action.type === 'reset') {
    return initialState()
  }

  if (action.type === 'connected') {
    return { ...state, connected: action.connected }
  }

  if (action.type === 'connection_error') {
    return { ...state, error: 'WebSocket connection failed.' }
  }

  if (action.type !== 'event') {
    return state
  }

  const event = action.event
  let next = state

  if (STREAM_EVENT_TYPES.has(event.type)) {
    next = { ...next, streamEvents: appendEvent(next.streamEvents, event) }
  }

  if (event.type === 'stage_start') {
    return {
      ...next,
      stages: { ...next.stages, [event.stage]: 'running' },
    }
  }

  if (event.type === 'stage_complete') {
    return {
      ...next,
      stages: { ...next.stages, [event.stage]: 'complete' },
    }
  }

  if (event.type === 'review_comment') {
    return {
      ...next,
      reviewComments: [
        ...next.reviewComments,
        { round: event.round, kind: event.kind, text: event.text },
      ],
    }
  }

  if (event.type === 'revision_start') {
    return { ...next, revisionRound: event.round }
  }

  if (event.type === 'run_complete') {
    return { ...next, result: event, stages: markAllStages('complete') }
  }

  if (event.type === 'run_error') {
    const stages = { ...next.stages }
    for (const [stage, status] of Object.entries(stages)) {
      if (status === 'running') {
        stages[stage] = 'error'
      }
    }
    return { ...next, error: event.error || 'Run failed.', stages }
  }

  if (event.type === 'raw') {
    return { ...next, streamEvents: appendEvent(next.streamEvents, event) }
  }

  return next
}

export function useRunStream(runId) {
  const [state, dispatch] = useReducer(reducer, null, initialState)

  useEffect(() => {
    dispatch({ type: 'reset' })

    if (!runId) {
      return undefined
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/runs/${runId}`)

    socket.onopen = () => dispatch({ type: 'connected', connected: true })
    socket.onclose = () => dispatch({ type: 'connected', connected: false })
    socket.onerror = () => dispatch({ type: 'connection_error' })

    socket.onmessage = (message) => {
      try {
        dispatch({ type: 'event', event: JSON.parse(message.data) })
      } catch {
        dispatch({ type: 'event', event: { type: 'raw', text: message.data } })
      }
    }

    return () => {
      socket.close()
    }
  }, [runId])

  return useMemo(() => state, [state])
}
