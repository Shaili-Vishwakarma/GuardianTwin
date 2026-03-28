import { useState, useEffect, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import FloorPlan from './components/FloorPlan'
import LogsPanel from './components/LogsPanel'
import OperatorQuery from './components/OperatorQuery'

const THREAT_COLORS = {
  none: '#22c55e', low: '#84cc16', medium: '#f59e0b',
  high: '#ef4444', critical: '#7f1d1d',
}

function playSiren(ctx) {
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.4, ctx.currentTime)
  gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 5)
  gain.connect(ctx.destination)
  for (let i = 0; i < 10; i++) {
    const osc = ctx.createOscillator()
    osc.type = 'sawtooth'
    osc.frequency.value = i % 2 === 0 ? 880 : 1320
    osc.connect(gain)
    osc.start(ctx.currentTime + i * 0.5)
    osc.stop(ctx.currentTime + i * 0.5 + 0.48)
  }
}

export default function App() {
  const { data: state, send } = useWebSocket('ws://localhost:8000/ws')
  const threat = state?.threat_level || 'none'

  const audioCtxRef = useRef(null)
  const sirenFired  = useRef(false)
  const [audioArmed, setAudioArmed] = useState(false)

  const armAudio = () => {
    if (audioCtxRef.current) return
    try {
      const ctx = new AudioContext()
      ctx.resume()
      audioCtxRef.current = ctx
      setAudioArmed(true)
      const buf = ctx.createBuffer(1, 1, 22050)
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(ctx.destination)
      src.start(0)
    } catch (e) {}
  }

  useEffect(() => {
    if (sirenFired.current) return
    if (!['medium', 'high', 'critical'].includes(threat)) return
    sirenFired.current = true
    const ctx = audioCtxRef.current
    if (ctx && ctx.state === 'running') playSiren(ctx)
  }, [threat])

  const occupants         = state?.occupant_positions || []
  const trapped           = occupants.filter(o => o.status === 'at_risk')
  const safe              = occupants.filter(o => o.status === 'safe')
  const unaccounted       = state?.unaccounted_count ?? 0
  const rescueAgents      = state?.rescue_agents || []
  const fireBrigade       = state?.fire_brigade || []
  const suppressionZones  = state?.suppression_active || []
  const extinguishedZones = state?.extinguished_zones || []
  const allClear = threat === 'none' && extinguishedZones.length > 0
    && trapped.length === 0 && unaccounted === 0
  const threatBg = allClear ? '#16a34a' : THREAT_COLORS[threat]

  return (
    <div style={{
      height: '100vh', overflow: 'hidden', background: '#020617', color: '#e2e8f0',
      fontFamily: 'monospace', display: 'flex', flexDirection: 'column',
      padding: '8px 14px', gap: 6, boxSizing: 'border-box',
    }}>

      {/* TOP BAR */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        borderBottom: '1px solid #1e293b', paddingBottom: 6, flexWrap: 'nowrap',
        minWidth: 0,
      }}>
        <span style={{ color: '#3b82f6', fontWeight: 'bold', fontSize: 19, whiteSpace: 'nowrap' }}>
          GuardianTwin
        </span>
        <div style={{
          background: threatBg, color: 'white', whiteSpace: 'nowrap',
          padding: '3px 14px', borderRadius: 20, fontSize: 16, fontWeight: 'bold',
        }}>
          {allClear ? 'ALL CLEAR' : 'THREAT: ' + threat.toUpperCase()}
        </div>
        {!allClear && state?.hvac_shutdown      && <Tag color='#f59e0b'>HVAC OFF</Tag>}
        {!allClear && state?.elevators_recalled && <Tag color='#f59e0b'>LIFTS RECALLED</Tag>}
        {!allClear && state?.emergency_lighting && <Tag color='#fbbf24'>EMRG LIGHTING</Tag>}
        {allClear && <Tag color='#22c55e'>Cleared: {extinguishedZones.join(', ')}</Tag>}
        {!state && <Tag color='#64748b'>Connecting...</Tag>}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          <button
            onClick={armAudio}
            style={{
              display: 'flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap',
              background: audioArmed ? '#052e16' : '#1c1400',
              border: '1px solid ' + (audioArmed ? '#16a34a' : '#ca8a04'),
              color: audioArmed ? '#4ade80' : '#fbbf24',
              padding: '5px 12px', borderRadius: 6,
              cursor: audioArmed ? 'default' : 'pointer',
              fontSize: 14, fontFamily: 'monospace',
            }}
          >
            {audioArmed ? '🔔 Armed' : '🔕 Siren'}
          </button>
          <OperatorQuery send={send} queryResponse={state?.query_response} />
          <LogsPanel />
        </div>
      </div>

      {/* STAT CARDS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 6, flexShrink: 0 }}>
        <StatCard label='TOTAL'          value={occupants.length} color='#94a3b8' />
        <StatCard label='TRAPPED'        value={trapped.length}   color='#ef4444' blink={trapped.length > 0} />
        <StatCard label='UNACCOUNTED'    value={unaccounted}      color='#f59e0b' />
        <StatCard label='SAFE'           value={safe.length}      color='#22c55e' />
      </div>

      {/* MAIN BODY */}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 8, flex: 1, minHeight: 0 }}>

        {/* LEFT: map */}
        <div style={{
          background: '#0f172a', borderRadius: 8, padding: 8,
          display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden',
          width: 'fit-content',
        }}>
          <FloorPlan state={state} />
        </div>

        {/* RIGHT: panels */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, minHeight: 0, overflow: 'hidden' }}>

          {/* Operations */}
          <div style={{ background: '#0f172a', borderRadius: 8, padding: '7px 12px', flexShrink: 0 }}>
            <SectionLabel>OPERATIONS</SectionLabel>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {rescueAgents.filter(a => a.status !== 'standby').map(a => (
                <AgentBadge key={a.id} id={a.id} color={a.color}
                  target={a.target || '—'}
                  statusLabel={
                    a.status === 'responding' ? 'responding'
                  : a.status === 'on_scene'   ? 'on scene'
                  : a.status === 'escorting'  ? 'escorting'
                  : a.status}
                />
              ))}
              {fireBrigade.filter(u => u.status !== 'standby').map(u => (
                <AgentBadge key={u.id} id={u.id} color={u.color}
                  target={u.target_zone || '—'}
                  statusLabel={
                    u.status === 'responding' ? 'responding'
                  : u.status === 'fighting'   ? 'fighting'
                  : u.status === 'returning'  ? 'returning'
                  : u.status}
                />
              ))}
              {rescueAgents.every(a => a.status === 'standby') && fireBrigade.every(u => u.status === 'standby') && (
                <span style={{ fontSize: 15, color: '#475569' }}>All units standby</span>
              )}
            </div>
            {suppressionZones.length > 0 && (
              <div style={{ fontSize: 15, color: '#38bdf8', marginTop: 5 }}>
                Sprinklers active: {suppressionZones.join(', ')}
              </div>
            )}
          </div>

          {/* Trapped people */}
          {trapped.length > 0 && (
            <div style={{
              background: '#1a0a0a', border: '1px solid #ef4444',
              borderRadius: 8, padding: '7px 12px', flexShrink: 0,
            }}>
              <div style={{ fontSize: 15, color: '#ef4444', fontWeight: 'bold', marginBottom: 5 }}>
                {trapped.length} TRAPPED
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {trapped.map(p => (
                  <span key={p.person_id} style={{
                    background: '#2d0a0a', border: '1px solid #ef444466',
                    borderRadius: 4, padding: '3px 8px', fontSize: 15, color: '#ef4444',
                  }}>
                    {p.person_id} <span style={{ color: '#94a3b8' }}>{p.zone}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Occupant roster */}
          <div style={{ background: '#0f172a', borderRadius: 8, padding: '7px 12px', flexShrink: 0 }}>
            <SectionLabel>OCCUPANTS</SectionLabel>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {occupants.map(o => {
                const c = o.status === 'at_risk' ? '#ef4444' : o.status === 'safe' ? '#22c55e' : '#f59e0b'
                return (
                  <span key={o.person_id} style={{
                    background: '#1e293b', border: '1px solid ' + c + '55',
                    borderRadius: 4, padding: '2px 7px', fontSize: 15,
                  }}>
                    <span style={{ color: c }}>{o.person_id}</span>
                    <span style={{ color: '#64748b' }}> {o.zone}</span>
                  </span>
                )
              })}
            </div>
          </div>

          {/* Live alerts */}
          <div style={{ background: '#0f172a', borderRadius: 8, padding: '7px 12px', flexShrink: 0 }}>
            <SectionLabel>LIVE ALERTS</SectionLabel>
            {(state?.active_alerts || []).slice(-3).reverse().map((a, i) => (
              <div key={i} style={{
                fontSize: 15, color: '#cbd5e1', borderLeft: '3px solid #ef4444',
                paddingLeft: 8, marginBottom: 4, lineHeight: 1.5,
              }}>
                <span style={{ color: '#ef4444', fontWeight: 'bold' }}>{a.person_id}: </span>
                {a.message}
              </div>
            ))}
            {!(state?.active_alerts?.length) && (
              <div style={{ fontSize: 15, color: '#334155' }}>No active alerts</div>
            )}
          </div>

          {/* Agent trace */}
          <div style={{
            background: '#0f172a', borderRadius: 8, padding: '7px 12px',
            flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column',
          }}>
            <SectionLabel>AGENT TRACE</SectionLabel>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {(state?.agent_action_log || []).slice(-40).reverse().map((l, i) => (
                <div key={i} style={{
                  fontSize: 15, color: logColor(l), marginBottom: 3,
                  borderBottom: '1px solid #0f172a', paddingBottom: 3,
                  lineHeight: 1.5, wordBreak: 'break-word',
                }}>
                  {l}
                </div>
              ))}
            </div>
          </div>

          {/* Status strip */}
          <div style={{
            background: '#0f172a', borderRadius: 8, padding: '6px 12px',
            flexShrink: 0, fontSize: 15, color: '#64748b',
            display: 'flex', gap: 14, flexWrap: 'wrap',
          }}>
            <span>Origin: <span style={{ color: '#f87171' }}>{state?.fire_origin_zone || '—'}</span></span>
            <span>Routes: <span style={{ color: '#34d399' }}>{Object.keys(state?.safe_routes || {}).length}</span></span>
            <span>Suppression: <span style={{ color: '#38bdf8' }}>{suppressionZones.join(', ') || 'none'}</span></span>
            <span>Extinguished: <span style={{ color: '#22c55e' }}>{extinguishedZones.join(', ') || 'none'}</span></span>
          </div>

        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
      `}</style>
    </div>
  )
}

function logColor(line) {
  if (line.includes('FireBrigade')) return '#f43f5e'
  if (line.includes('RescueSim') || line.includes('TrackSense')) return '#a78bfa'
  if (line.includes('SystemCtrl')) return '#38bdf8'
  if (line.includes('FireSense')) return '#fb923c'
  if (line.includes('Orchestrator')) return '#facc15'
  if (line.includes('CommRelay')) return '#34d399'
  return '#94a3b8'
}

function SectionLabel({ children }) {
  return (
    <div style={{ fontSize: 15, color: '#475569', marginBottom: 5, letterSpacing: '0.05em' }}>
      {children}
    </div>
  )
}

function Tag({ color, children }) {
  return (
    <span style={{
      color, fontSize: 14, whiteSpace: 'nowrap',
      background: color + '18', border: '1px solid ' + color + '55',
      borderRadius: 5, padding: '3px 10px',
    }}>
      {children}
    </span>
  )
}

function AgentBadge({ id, color, target, statusLabel }) {
  return (
    <div style={{
      background: '#1e293b', border: '1px solid ' + color,
      borderRadius: 5, padding: '3px 9px', fontSize: 15,
      display: 'flex', gap: 5, alignItems: 'center',
    }}>
      <span style={{ color, fontWeight: 'bold' }}>{id}</span>
      <span style={{ color: '#475569' }}>-&gt;</span>
      <span style={{ color: '#e2e8f0' }}>{target}</span>
      <span style={{ color: '#94a3b8' }}>{statusLabel}</span>
    </div>
  )
}

function StatCard({ label, value, color, blink }) {
  return (
    <div style={{
      background: '#0f172a', borderRadius: 6, padding: '6px 10px',
      border: '1px solid ' + color + '33',
      animation: blink ? 'pulse 1.5s infinite' : 'none',
    }}>
      <div style={{ fontSize: 15, color: '#64748b', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 'bold', color }}>{value}</div>
    </div>
  )
}
