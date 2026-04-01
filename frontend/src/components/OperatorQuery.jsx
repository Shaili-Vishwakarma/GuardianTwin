import { useState, useRef, useEffect, useCallback } from 'react'

function useDrag(initialPos) {
  const [pos, setPos] = useState(initialPos)
  const dragging = useRef(false)
  const offset   = useRef({ x: 0, y: 0 })

  const onMouseDown = useCallback((e) => {
    dragging.current = true
    offset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }
    e.preventDefault()
  }, [pos])

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return
      setPos({ x: e.clientX - offset.current.x, y: e.clientY - offset.current.y })
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  return { pos, onMouseDown }
}

const THINKING_STEPS = [
  '⚡ Parsing query...',
  '🔍 Scanning sensor data...',
  '📍 Locating occupants...',
  '🧠 Analysing emergency state...',
  '📡 Routing to CommRelay...',
]

export default function OperatorQuery({ send, queryResponse }) {
  const [open, setOpen]       = useState(false)
  const [query, setQuery]     = useState('')
  const [thinking, setThinking] = useState(false)
  const [thinkStep, setThinkStep] = useState(0)
  const [lastQuery, setLastQuery] = useState('')
  const [localResponse, setLocalResponse] = useState(null)
  const thinkTimer   = useRef(null)
  const { pos, onMouseDown } = useDrag({ x: window.innerWidth - 730, y: window.innerHeight - 520 })

  // Detect when a new response arrives — not used for HTTP path, kept for WS fallback
  useEffect(() => {
    if (queryResponse && !localResponse) {
      setThinking(false)
      clearInterval(thinkTimer.current)
    }
  }, [queryResponse])

  // Animate thinking steps
  useEffect(() => {
    if (thinking) {
      setThinkStep(0)
      thinkTimer.current = setInterval(() => {
        setThinkStep(s => (s + 1) % THINKING_STEPS.length)
      }, 600)
    } else {
      clearInterval(thinkTimer.current)
    }
    return () => clearInterval(thinkTimer.current)
  }, [thinking])

  const submit = async () => {
    if (!query.trim()) return
    const q = query.trim()
    setLastQuery(q)
    setThinking(true)
    setLocalResponse(null)
    setQuery('')
    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: q }),
      })
      const data = await res.json()
      setLocalResponse(data.response)
    } catch (e) {
      setLocalResponse('⚠ Could not reach backend.')
    } finally {
      setThinking(false)
      clearInterval(thinkTimer.current)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: open ? '#1a2e1a' : '#0f172a',
          border: `1px solid ${open ? '#22c55e' : '#334155'}`,
          color: open ? '#4ade80' : '#94a3b8',
          padding: '5px 14px', borderRadius: 6,
          cursor: 'pointer', fontSize: 15, fontFamily: 'monospace',
          transition: 'all 0.15s',
        }}
      >
        <span style={{ fontSize: 16 }}>🎙</span> Query
      </button>

      {open && (
        <div style={{
          position: 'fixed', left: pos.x, top: pos.y,
          width: 700,
          background: '#0a0f1e',
          border: '1px solid #1a3a1a',
          borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
          display: 'flex', flexDirection: 'column',
          zIndex: 1001,
          fontFamily: 'monospace',
          resize: 'both', overflow: 'hidden',
          minWidth: 400, minHeight: 300,
        }}>
          {/* Draggable header */}
          <div
            onMouseDown={onMouseDown}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 14px',
              borderBottom: '1px solid #1e293b',
              background: '#0f172a', borderRadius: '10px 10px 0 0',
              cursor: 'grab', userSelect: 'none',
            }}
          >
            <span style={{ color: '#4ade80', fontSize: 15, fontWeight: 'bold' }}>🎙 Operator Query</span>
            <span style={{ color: '#334155', fontSize: 12, marginLeft: 4 }}>⠿ drag</span>
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={() => setOpen(false)}
              style={{
                marginLeft: 'auto', background: 'none', border: 'none',
                color: '#64748b', cursor: 'pointer', fontSize: 18, lineHeight: 1,
              }}
            >✕</button>
          </div>

          {/* Input */}
          <div style={{ padding: '14px 16px', display: 'flex', gap: 8 }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder='e.g. How many people are trapped?'
              autoFocus
              style={{
                flex: 1, background: '#1e293b', border: '1px solid #334155',
                color: '#e2e8f0', padding: '9px 14px', borderRadius: 6,
                fontSize: 16, outline: 'none',
              }}
            />
            <button
              onClick={submit}
              disabled={thinking}
              style={{
                background: thinking ? '#166534' : '#22c55e',
                color: thinking ? '#4ade80' : '#000',
                border: 'none',
                padding: '9px 20px', borderRadius: 6,
                cursor: thinking ? 'not-allowed' : 'pointer',
                fontSize: 16, fontWeight: 'bold',
                transition: 'all 0.2s',
              }}
            >{thinking ? '...' : 'Ask'}</button>
          </div>

          {/* Thinking process */}
          {thinking && (
            <div style={{
              margin: '0 16px 10px',
              padding: '10px 14px',
              background: '#0d1f0d',
              border: '1px solid #166534',
              borderRadius: 8,
              fontSize: 15,
            }}>
              <div style={{ color: '#4ade80', marginBottom: 6, fontWeight: 'bold' }}>
                ⚙ Processing query: <span style={{ color: '#86efac' }}>"{lastQuery}"</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {THINKING_STEPS.map((step, i) => (
                  <div key={i} style={{
                    color: i < thinkStep ? '#22c55e' : i === thinkStep ? '#86efac' : '#1a4a1a',
                    fontSize: 14,
                    transition: 'color 0.3s',
                  }}>
                    {i < thinkStep ? '✓' : i === thinkStep ? '▶' : '○'} {step}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Response */}
          <div style={{
            minHeight: 200, maxHeight: 420,
            margin: `0 16px 16px`,
            padding: '12px 14px',
            background: '#0f172a', border: '1px solid #1e293b',
            borderRadius: 8, overflowY: 'auto',
            fontSize: 16, color: '#7dd3fc', lineHeight: 1.7,
          }}>
            {localResponse && !thinking ? (
              <>
                <div style={{
                  fontSize: 13, color: '#22c55e', marginBottom: 8,
                  borderBottom: '1px solid #1e293b', paddingBottom: 6,
                }}>
                  ⚡ Answered by rule-based engine
                </div>
                {localResponse}
              </>
            ) : !thinking ? (
              <span style={{ color: '#334155' }}>Response will appear here…</span>
            ) : null}
          </div>
        </div>
      )}
    </>
  )
}
