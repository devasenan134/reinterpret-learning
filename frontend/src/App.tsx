import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('checking…')
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setStatus(d.ok ? 'backend connected' : 'backend error'))
      .catch(() => setStatus('backend unreachable'))
  }, [])
  return <p>reinterpret {status}</p>
}
