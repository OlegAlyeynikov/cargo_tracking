import { useState } from 'react'
import DropZone from './components/DropZone'
import ResultsTable from './components/ResultsTable'
import { trackFile, trackJson } from './services/api'
import { exportToExcel } from './services/export'

const DEFAULT_JSON = `{
  "shipments": [
    {"id": "test-1", "number": "501-20285134"},
    {"id": "test-2", "number": "TLLU4912250"}
  ]
}`

export default function App() {
  const [mode, setMode] = useState('file')
  const [file, setFile] = useState(null)
  const [json, setJson] = useState(DEFAULT_JSON)
  const [webhookUrl, setWebhookUrl] = useState('')
  const [debug, setDebug] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [response, setResponse] = useState(null)

  const submit = async () => {
    setError(null)
    setLoading(true)
    try {
      const opts = { webhookUrl: webhookUrl || undefined, debug }
      const data = mode === 'file'
        ? await trackFile(file, opts)
        : await trackJson(JSON.parse(json).shipments, opts)
      setResponse(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const canSubmit = !loading && (mode === 'json' ? json.trim() : !!file)

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center gap-3">
          <span className="text-2xl">✈️</span>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Cargo Tracking</h1>
            <p className="text-xs text-gray-400">AWB & Sea Container Tracker</p>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">

        {/* Input card */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">

          {/* Mode tabs */}
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
            {['file', 'json'].map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors
                  ${mode === m ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
              >
                {m === 'file' ? 'Upload File' : 'Paste JSON'}
              </button>
            ))}
          </div>

          {/* Input area */}
          {mode === 'file'
            ? <DropZone onFile={setFile} />
            : <textarea
                value={json}
                onChange={e => setJson(e.target.value)}
                rows={10}
                spellCheck={false}
                className="w-full font-mono text-sm border border-gray-300 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              />
          }

          {/* Options row */}
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-52">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Webhook URL <span className="text-gray-400">(optional)</span>
              </label>
              <input
                type="url"
                placeholder="https://your-server.com/webhook"
                value={webhookUrl}
                onChange={e => setWebhookUrl(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer select-none mb-2">
              <input
                type="checkbox"
                checked={debug}
                onChange={e => setDebug(e.target.checked)}
                className="w-4 h-4 accent-blue-600"
              />
              <span className="text-sm text-gray-600">Debug mode</span>
            </label>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="mb-2 px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium
                hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Tracking…' : 'Track'}
            </button>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Results */}
        {response && (
          <div className="space-y-4">

            {/* Summary bar */}
            <div className="flex items-center justify-between">
              <div className="flex gap-4 text-sm">
                <span className="text-gray-500">Total: <b className="text-gray-900">{response.summary.total}</b></span>
                <span className="text-green-600">Success: <b>{response.summary.success}</b></span>
                <span className="text-red-500">Failed: <b>{response.summary.failed}</b></span>
                <span className="text-gray-400 text-xs self-center">{response.checked_at?.slice(0, 19).replace('T', ' ')} UTC</span>
              </div>
              <button
                onClick={() => exportToExcel(response.results)}
                className="flex items-center gap-2 px-4 py-1.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors"
              >
                <span>↓</span> Export Excel
              </button>
            </div>

            <ResultsTable results={response.results} />

            {/* Debug panel */}
            {debug && (
              <details className="bg-gray-900 rounded-xl p-4">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-200">
                  Raw JSON response
                </summary>
                <pre className="text-xs text-green-400 mt-3 overflow-auto max-h-96">
                  {JSON.stringify(response, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
