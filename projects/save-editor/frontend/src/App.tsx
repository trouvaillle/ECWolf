import { useState, useCallback, useEffect } from 'react'

interface SaveInfo {
  path: string
  metadata: Record<string, string>
  saveVersion: number
  saveProdVersion: number
  snapSize: number
  snapDecompressedSize: number
  hasScreenshot: boolean
}

type Tab = 'info' | 'meta' | 'hex'

const API = ''

async function api(path: string, options?: RequestInit) {
  const res = await fetch(API + path, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || res.statusText)
  }
  return res.json()
}

function formatVersion(v: number): string {
  const major = (v >> 20) & 0xFFF
  const minor = (v >> 8) & 0xFFF
  const patch = v & 0xFF
  return `${major}.${minor}.${patch}`
}

function formatSaveVersion(v: number): string {
  if (v >= 99999999999) return 'Unknown'
  const d = new Date(v * 1000)
  return d.toISOString().replace('T', ' ').slice(0, 19)
}

export default function App() {
  const [saveInfo, setSaveInfo] = useState<SaveInfo | null>(null)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<Tab>('info')
  const [editedMeta, setEditedMeta] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [savePath, setSavePath] = useState('')
  const [manualPath, setManualPath] = useState('')

  const loadFile = useCallback(async (path: string) => {
    setLoading(true)
    setError(null)
    try {
      const info = await api('/api/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      setSaveInfo(info)
      setSavePath(path)
      setEditedMeta({ ...info.metadata })

      if (info.hasScreenshot) {
        const img = await api('/api/screenshot')
        setScreenshot(img.image)
      } else {
        setScreenshot(null)
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    api('/api/info')
      .then(info => {
        setSaveInfo(info)
        setSavePath(info.path)
        setEditedMeta({ ...info.metadata })
        if (info.hasScreenshot) {
          api('/api/screenshot').then((img: any) => setScreenshot(img.image)).catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  const handleOpenFile = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api('/api/browse', { method: 'POST' })
      if (!result.cancelled) {
        setSaveInfo(result)
        setSavePath(result.path)
        setEditedMeta({ ...result.metadata })
        if (result.hasScreenshot) {
          const img = await api('/api/screenshot')
          setScreenshot(img.image)
        }
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleOpenManualPath = async () => {
    if (!manualPath.trim()) return
    await loadFile(manualPath.trim())
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const result = await api('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: savePath,
          metadata: editedMeta,
        }),
      })
      setSaveInfo(result)
      setEditedMeta({ ...result.metadata })
      alert('Save file updated!')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const metaKeys = saveInfo ? Object.keys(saveInfo.metadata) : []

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'Segoe UI, sans-serif', background: '#1a1a2e', color: '#eee' }}>
      <header style={{ padding: '12px 20px', background: '#16213e', borderBottom: '1px solid #0f3460', display: 'flex', alignItems: 'center', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20, color: '#e94560' }}>ECWolf Save Editor</h1>
        <button onClick={handleOpenFile} style={btnStyle}>Open .ecs</button>
        {saveInfo && (
          <button onClick={handleSave} disabled={saving} style={btnStyle}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        )}
        {error && <span style={{ color: '#ff6b6b', marginLeft: 12 }}>{error}</span>}
        {loading && <span style={{ marginLeft: 12, color: '#888' }}>Loading...</span>}
      </header>

      {!saveInfo ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#666' }}>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: 18, marginBottom: 16 }}>Open an ECWolf save file (.ecs) to begin</p>
            <button onClick={handleOpenFile} style={{ ...btnStyle, fontSize: 16, padding: '10px 24px' }}>Browse...</button>
            <div style={{ marginTop: 16, display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
              <span style={{ fontSize: 13 }}>or enter path:</span>
              <input
                value={manualPath}
                onChange={e => setManualPath(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleOpenManualPath()}
                placeholder="C:\Users\USER\Saved Games\ECWolf\savegam0.ecs"
                style={{ ...inputStyle, width: 360 }}
              />
              <button onClick={handleOpenManualPath} style={btnStyle}>Open</button>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: 280, background: '#16213e', padding: 16, overflow: 'auto', borderRight: '1px solid #0f3460' }}>
            {screenshot && (
              <div style={{ marginBottom: 16 }}>
                <img src={screenshot} alt="Screenshot" style={{ width: '100%', borderRadius: 4, imageRendering: 'pixelated' }} />
              </div>
            )}
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>File</div>
            <div style={{ fontSize: 13, wordBreak: 'break-all', marginBottom: 12 }}>{saveInfo.path}</div>

            <div style={infoRowStyle}>Engine</div>
            <div style={infoValStyle}>{saveInfo.metadata['Engine'] || '-'}</div>

            <div style={infoRowStyle}>Game WAD</div>
            <div style={infoValStyle}>{saveInfo.metadata['Game WAD'] || '-'}</div>

            <div style={infoRowStyle}>Map WAD</div>
            <div style={infoValStyle}>{saveInfo.metadata['Map WAD'] || '-'}</div>

            <div style={{ fontSize: 12, color: '#888', marginTop: 16, marginBottom: 4 }}>Versions</div>
            <div style={infoRowStyle}>Save Version</div>
            <div style={infoValStyle}>{formatSaveVersion(saveInfo.saveVersion)}</div>
            <div style={infoRowStyle}>Product</div>
            <div style={infoValStyle}>{formatVersion(saveInfo.saveProdVersion)}</div>
            <div style={infoRowStyle}>snAp</div>
            <div style={infoValStyle}>{saveInfo.snapSize} bytes &rarr; {saveInfo.snapDecompressedSize} bytes</div>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', borderBottom: '1px solid #0f3460' }}>
              {(['info', 'meta'] as Tab[]).map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    ...tabBtnStyle,
                    background: tab === t ? '#0f3460' : 'transparent',
                    borderBottom: tab === t ? '2px solid #e94560' : '2px solid transparent',
                  }}
                >
                  {t === 'info' ? 'Game Info' : 'Metadata'}
                </button>
              ))}
            </div>

            <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
              {tab === 'info' && (
                <div>
                  <Section title="Current Map">
                    <Field label="Map" value={saveInfo.metadata['Current Map'] || '-'} />
                    <Field label="Title" value={saveInfo.metadata['Title'] || '-'} />
                    <Field label="Comment" value={saveInfo.metadata['Comment'] || '-'} />
                    <Field label="Creation Time" value={saveInfo.metadata['Creation Time'] || '-'} />
                  </Section>
                </div>
              )}

              {tab === 'meta' && (
                <div>
                  <p style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
                    Edit metadata fields below. Changes are applied when you click "Save".
                  </p>
                  {metaKeys.map(key => {
                    const editable = ['Title'].includes(key)
                    return (
                      <div key={key} style={{ marginBottom: 8 }}>
                        <label style={{ display: 'block', fontSize: 11, color: '#888', marginBottom: 2 }}>{key}</label>
                        {editable ? (
                          <input
                            value={editedMeta[key] || ''}
                            onChange={e => setEditedMeta(prev => ({ ...prev, [key]: e.target.value }))}
                            style={inputStyle}
                          />
                        ) : (
                          <div style={{ fontSize: 13, color: '#ccc', padding: '4px 0' }}>{saveInfo.metadata[key] || ''}</div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e94560', textTransform: 'uppercase', letterSpacing: 1 }}>{title}</h3>
      {children}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 8, display: 'flex' }}>
      <div style={{ width: 140, fontSize: 12, color: '#888', flexShrink: 0 }}>{label}</div>
      <div style={{ fontSize: 13 }}>{value}</div>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  background: '#e94560',
  color: '#fff',
  border: 'none',
  padding: '6px 16px',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
}

const tabBtnStyle: React.CSSProperties = {
  padding: '10px 20px',
  color: '#eee',
  border: 'none',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
}

const infoRowStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#888',
  marginTop: 4,
}

const infoValStyle: React.CSSProperties = {
  fontSize: 13,
  marginBottom: 4,
  wordBreak: 'break-all',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 8px',
  borderRadius: 4,
  border: '1px solid #0f3460',
  background: '#1a1a2e',
  color: '#eee',
  fontSize: 13,
  boxSizing: 'border-box',
}
