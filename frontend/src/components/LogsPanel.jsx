import { useState, useEffect, useRef, useCallback } from 'react'

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

export default function LogsPanel() {
  const [open, setOpen]   = useState(false)
  const [lines, setLines] = useState([])
  const [filter, setFilter] = useState('')
  const bottomRef = useRef(null)
  const esRef     = useRef(null)
  const { pos, onMouseDown } = useDrag({ x: window.innerWidth - 650, y: window.innerHeight - 420 })

  useEffect(() => {
    if (!open) return

    // Fetch history first
    fetch('http://localhost:8000/logs/history')
      .then(r => r.json())
      .then(d => setLines(d.lines || []))
      .catch(() => {})

    // Then stream new lines via SSE
    const es = new EventSource('http://localhost:8000/logs/stream')
    esRef.current = es
    es.onmessage = e => {
      setLines(prev => {
        const next = [...prev, e.data]
        return next.length > 500 ? next.slice(-500) : next
      })
    }
    return () => { es.close(); esRef.current = null }
  }, [open])

  // Auto-scroll to bottom
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, open])

  const filtered = filter
    ? lines.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    : lines

  function lineColor(l) {
    if (l.includes('ERROR') || l.includes('error'))   return '#f87171'
    if (l.includes('RESCUED') || l.includes('✅'))    return '#34d399'
    if (l.includes('Threat=high') || l.includes('Threat=critical')) return '#ef4444'
    if (l.includes('Threat=medium'))                  return '#f59e0b'
    if (l.includes('[RescueSim]'))                    return '#a78bfa'
    if (l.includes('[FireSense]'))                    return '#fb923c'
    if (l.includes('[TrackSense]'))                   return '#38bdf8'
    if (l.includes('[RoutePilot]'))                   return '#4ade80'
    if (l.includes('[SystemCtrl]'))                   return '#fbbf24'
    if (l.includes('[CommRelay]'))                    return '#e879f9'
    if (l.includes('[Orchestrator]'))                 return '#60a5fa'
    if (l.includes('[SIM]'))                          return '#94a3b8'
    return '#64748b'
  }

  return (
    <>
      {/* Logs button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: open ? '#1e3a5f' : '#0f172a',
          border: `1px solid ${open ? '#3b82f6' : '#334155'}`,
          color: open ? '#60a5fa' : '#94a3b8',
          padding: '5px 14px', borderRadius: 6,
          cursor: 'pointer', fontSize: 14, fontFamily: 'monospace',
          transition: 'all 0.15s',
        }}
      >
        <span style={{ fontSize: 14 }}>📋</span> Logs
        {lines.length > 0 && (
          <span style={{
            background: '#1e3a5f', color: '#60a5fa',
            borderRadius: 10, padding: '1px 6px', fontSize: 15,
          }}>{lines.length}</span>
        )}
      </button>

      {/* Floating log panel */}
      {open && (
        <div style={{
          position: 'fixed', left: pos.x, top: pos.y,
          width: 620, height: 380,
          background: '#0a0f1e',
          border: '1px solid #1e3a5f',
          borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
          display: 'flex', flexDirection: 'column',
          zIndex: 1000,
          fontFamily: 'monospace',
          resize: 'both', overflow: 'hidden',
          minWidth: 400, minHeight: 280,
        }}>
          {/* Header */}
          <div
            onMouseDown={onMouseDown}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 12px',
              borderBottom: '1px solid #1e293b',
              background: '#0f172a', borderRadius: '10px 10px 0 0',
              cursor: 'grab', userSelect: 'none',
            }}
          >
            <span style={{ color: '#60a5fa', fontSize: 15, fontWeight: 'bold' }}>📋 Backend Logs</span>
            <span style={{ color: '#334155', fontSize: 14, marginLeft: 4 }}>⠿ drag</span>
            <input
              value={filter}
              onChange={e => setFilter(e.target.value)}
              placeholder='filter...'
              style={{
                flex: 1, background: '#1e293b', border: '1px solid #334155',
                color: '#e2e8f0', padding: '3px 8px', borderRadius: 4, fontSize: 14,
              }}
            />
            <button
              onClick={() => setLines([])}
              style={{
                background: 'none', border: '1px solid #334155',
                color: '#64748b', padding: '2px 8px', borderRadius: 4,
                cursor: 'pointer', fontSize: 14,
              }}
            >clear</button>
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={() => setOpen(false)}
              style={{
                background: 'none', border: 'none',
                color: '#64748b', cursor: 'pointer', fontSize: 16, lineHeight: 1,
              }}
            >✕</button>
          </div>

          {/* Log lines */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: '8px 12px',
            fontSize: 14, lineHeight: 1.7,
          }}>
            {filtered.length === 0 && (
              <div style={{ color: '#334155' }}>No logs yet...</div>
            )}
            {filtered.map((line, i) => (
              <div key={i} style={{ color: lineColor(line), whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {line}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Footer */}
          <div style={{
            padding: '4px 12px', borderTop: '1px solid #1e293b',
            fontSize: 15, color: '#334155',
          }}>
            {filtered.length} lines {filter && `(filtered from ${lines.length})`}
          </div>
        </div>
      )}
    </>
  )
}
