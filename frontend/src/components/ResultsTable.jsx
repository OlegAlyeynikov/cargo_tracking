import { useState } from 'react'
import StatusBadge from './StatusBadge'

function EventsDrawer({ events }) {
  if (!events?.length) return <p className="text-xs text-gray-400 p-3">No events</p>
  return (
    <div className="bg-gray-50 px-4 py-3 space-y-1">
      {events.map((ev, i) => (
        <div key={i} className="flex gap-3 text-xs text-gray-700">
          <span className="w-28 shrink-0 text-gray-400">{ev.datetime || '—'}</span>
          <span className="w-20 shrink-0">
            <StatusBadge status={ev.normalized_status} label={ev.event_code || ev.normalized_status} />
          </span>
          <span className="font-medium">{ev.event_name}</span>
          {ev.location && <span className="text-gray-400">{ev.location}</span>}
        </div>
      ))}
    </div>
  )
}

function Row({ r }) {
  const [open, setOpen] = useState(false)
  const t = r.tracking || {}
  const last = t.last_event || {}
  const errors = r.errors || []
  const hasData = !!r.tracking
  const changed = r.status_change?.changed

  return (
    <>
      <tr className={`border-b hover:bg-gray-50 transition-colors ${!hasData ? 'opacity-70' : ''}`}>
        <td className="px-3 py-2 font-mono text-sm font-medium text-gray-900">
          {r.input?.number}
          {changed && (
            <span className="ml-2 text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded font-sans">
              changed
            </span>
          )}
        </td>
        <td className="px-3 py-2">
          <span className="text-xs text-gray-500">{r.detected?.type?.replace('_', ' ')}</span>
        </td>
        <td className="px-3 py-2 text-xs text-gray-600">
          {r.detected?.carrier?.name || '—'}
        </td>
        <td className="px-3 py-2">
          {hasData
            ? <div>
                <StatusBadge status={t.current_status} />
                {t.current_status_ua && (
                  <div className="text-xs text-gray-400 mt-0.5">{t.current_status_ua}</div>
                )}
              </div>
            : <span className="text-xs text-gray-400">—</span>
          }
        </td>
        <td className="px-3 py-2 text-xs text-gray-600">
          {last.event_name
            ? <div>
                <div>{last.event_name}</div>
                {last.location && <div className="text-gray-400">{last.location}</div>}
                {last.datetime && <div className="text-gray-400">{last.datetime}</div>}
              </div>
            : '—'
          }
        </td>
        <td className="px-3 py-2">
          {errors.length > 0
            ? <div className="space-y-0.5">
                {errors.map((e, i) => (
                  <span key={i} className="block text-xs bg-red-50 text-red-700 px-1.5 py-0.5 rounded">
                    {e.code}
                  </span>
                ))}
              </div>
            : <span className="text-xs text-green-600">OK</span>
          }
        </td>
        <td className="px-3 py-2 text-center">
          {t.events?.length > 0 && (
            <button
              onClick={() => setOpen(o => !o)}
              className="text-xs text-blue-600 hover:underline"
            >
              {t.events.length} {open ? '▲' : '▼'}
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b">
          <td colSpan={7} className="p-0">
            <EventsDrawer events={t.events} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function ResultsTable({ results }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead className="bg-gray-100 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-3 py-2 text-left">Number</th>
            <th className="px-3 py-2 text-left">Type</th>
            <th className="px-3 py-2 text-left">Carrier</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2 text-left">Last Event</th>
            <th className="px-3 py-2 text-left">Errors</th>
            <th className="px-3 py-2 text-center">Events</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => <Row key={i} r={r} />)}
        </tbody>
      </table>
    </div>
  )
}
