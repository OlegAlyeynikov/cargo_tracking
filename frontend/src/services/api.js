const BASE = '/api/v1'

export async function trackJson(shipments, { webhookUrl, debug } = {}) {
  const body = { shipments }
  if (webhookUrl) body.webhook_url = webhookUrl

  const res = await fetch(`${BASE}/track${debug ? '?debug=true' : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`)
  return res.json()
}

export async function trackFile(file, { webhookUrl, debug } = {}) {
  const form = new FormData()
  form.append('file', file)
  if (webhookUrl) form.append('webhook_url', webhookUrl)

  const res = await fetch(`${BASE}/track/file${debug ? '?debug=true' : ''}`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`)
  return res.json()
}
