import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import FloorPlan from './components/FloorPlan'

const COLORS = {
  none: '#22c55e', low: '#84cc16', medium: '#f59e0b',
  high: '#ef4444', critical: '#7f1d1d',
}

const panel = {
  background: '#0f172a', borderRadius: 8, padding: 16,
}

export default function App() {
  const { data: state, send } = useWebSocket('ws://localhost:8000/ws')
  const [query, setQuery] = useState('')
  const threat = state?.threat_level || 'none'

  const submit = () => {
    if (!query.trim()) return
    send({ type: 'query', text: query })
    setQuery('')
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#020617', color: '#e2e8f0',
      fontFamily: 'monospace', padding: 24,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <h1 style={{ margin: 0, color: '#3b82f6', fontSize: 22 }}>GuardianTwin</h1>
        <div style={{
          background: COLORS[threat], color: 'white',
          padding: '4px 16px', borderRadius: 20, fontSize: 13, fontWeight: 'bold',
        }}>
          THREAT: {threat.toUpperCase()}
        </div>
        {state?.hvac_shutdown && (
          <span style={{ color: '#f59e0b', fontSize: 12 }}>HVAC OFF</span>
        )}
        {state?.elevators_recalled && (
          <span style={{ color: '#f59e0b', fontSize: 12 }}>ELEVATORS RECALLED</span>
        )}
        {state?.emergency_lighting && (
          <span style={{ color: '#fbbf24', fontSize: 12 }}>EMERGENCY LIGHTING ON</span>
        )}
        {!state && (
          <span style={{ color: '#64748b', fontSize: 12 }}>Connecting to server...</span>
        )}
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 24 }}>
        <FloorPlan state={state} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* NL Query */}
          <div style={panel}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>OPERATOR QUERY</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submit()}
                placeholder='How many people are unaccounted for?'
                style={{
                  flex: 1, background: '#1e293b', border: '1px solid #334155',
                  color: '#e2e8f0', padding: '8px 12px', borderRadius: 6, fontSize: 13,
                }}
              />
              <button onClick={submit} style={{
                background: '#3b82f6', color: 'white', border: 'none',
                padding: '8px 16px', borderRadius: 6, cursor: 'pointer',
              }}>Ask</button>
            </div>
            {state?.query_response && (
              <div style={{
                marginTop: 12, padding: 12, background: '#1e293b', borderRadius: 6,
                fontSize: 13, color: '#7dd3fc', lineHeight: 1.6,
              }}>
                {state.query_response}
              </div>
            )}
          </div>

          {/* Live Alerts */}
          <div style={panel}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>LIVE ALERTS</div>
            {(state?.active_alerts || []).slice(-5).reverse().map((a, i) => (
              <div key={i} style={{
                marginBottom: 8, padding: 8, background: '#1e293b', borderRadius: 6,
                fontSize: 12, borderLeft: '3px solid #ef4444',
              }}>
                <span style={{ color: '#ef4444', fontWeight: 'bold' }}>{a.person_id}: </span>
                {a.message}
              </div>
            ))}
            {!(state?.active_alerts?.length) && (
              <div style={{ fontSize: 12, color: '#334155' }}>No active alerts</div>
            )}
          </div>

          {/* Agent Trace */}
          <div style={panel}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>AGENT TRACE</div>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {(state?.agent_action_log || []).slice(-20).reverse().map((l, i) => (
                <div key={i} style={{
                  fontSize: 11, color: '#94a3b8', marginBottom: 4,
                  borderBottom: '1px solid #1e293b', paddingBottom: 4,
                }}>
                  {l}
                </div>
              ))}
              {!(state?.agent_action_log?.length) && (
                <div style={{ fontSize: 11, color: '#334155' }}>Waiting for agent activity...</div>
              )}
            </div>
          </div>

          {/* Stats */}
          <div style={panel}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>STATUS</div>
            <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 2 }}>
              <div>Fire origin: <span style={{ color: '#f87171' }}>{state?.fire_origin_zone || '—'}</span></div>
              <div>Unaccounted: <span style={{ color: '#fbbf24' }}>{state?.unaccounted_count ?? '—'}</span></div>
              <div>Routes computed: <span style={{ color: '#34d399' }}>{Object.keys(state?.safe_routes || {}).length}</span></div>
              <div>Suppression active: <span style={{ color: '#f87171' }}>{(state?.suppression_active || []).join(', ') || 'none'}</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
