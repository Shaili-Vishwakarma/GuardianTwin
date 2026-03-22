import { useState, useEffect, useRef } from 'react'

export function useWebSocket(url) {
  const [data, setData] = useState(null)
  const ws = useRef(null)

  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket(url)
      ws.current.onmessage = e => setData(JSON.parse(e.data))
      ws.current.onclose   = () => setTimeout(connect, 2000) // auto-reconnect
      ws.current.onerror   = () => ws.current.close()
    }
    connect()
    return () => ws.current?.close()
  }, [url])

  const send = msg =>
    ws.current?.readyState === 1 && ws.current.send(JSON.stringify(msg))

  return { data, send }
}
