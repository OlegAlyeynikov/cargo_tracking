import * as XLSX from 'xlsx'

export function exportToExcel(results) {
  const rows = results.map(r => {
    const t = r.tracking || {}
    const last = t.last_event || {}
    const errors = r.errors?.map(e => e.code).join(', ') || ''
    const carrier = r.detected?.carrier?.name || ''

    return {
      'Number': r.input?.number || '',
      'ID': r.input?.id || '',
      'Type': r.detected?.type || '',
      'Carrier': carrier,
      'Status': t.current_status || '',
      'Status (UA)': t.current_status_ua || '',
      'Last Event': last.event_name || '',
      'Location': last.location || '',
      'Date': last.datetime || '',
      'Events': t.events?.length || 0,
      'ETD': t.dates?.etd || '',
      'ETA': t.dates?.eta || '',
      'Status Changed': r.status_change?.changed ? 'YES' : 'NO',
      'Previous Status': r.status_change?.previous_status || '',
      'Delay Detected': r.delay?.delay_detected ? 'YES' : 'NO',
      'Risk Level': r.delay?.risk_level || '',
      'Errors': errors,
    }
  })

  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Tracking Results')

  const col_widths = Object.keys(rows[0] || {}).map(key => ({
    wch: Math.max(key.length, ...rows.map(r => String(r[key] || '').length)) + 2
  }))
  ws['!cols'] = col_widths

  XLSX.writeFile(wb, `cargo-tracking-${new Date().toISOString().slice(0, 10)}.xlsx`)
}
