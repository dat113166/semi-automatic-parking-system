// Lightweight API client skeleton for the frontend
// Uses Vite env: import.meta.env.VITE_BACKEND_URL and VITE_BACKEND_SECRET (for demo only)

const BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_BACKEND_URL)
  ? import.meta.env.VITE_BACKEND_URL.replace(/\/$/, '')
  : ''

function buildHeaders(extraHeaders = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  }
  // WARNING: For demo flows only. In production, do NOT expose backend secret on frontend.
  if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_BACKEND_SECRET) {
    headers['X-Secret'] = import.meta.env.VITE_BACKEND_SECRET
  }
  // Add auth token for staff when auth is implemented (e.g., Authorization: Bearer <token>)
  return headers
}

async function http(method, path, { query, body, headers } = {}) {
  if (!BASE_URL) {
    throw new Error('VITE_BACKEND_URL is not configured')
  }
  const url = new URL(`${BASE_URL}${path}`)
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    })
  }
  const res = await fetch(url.toString(), {
    method,
    headers: buildHeaders(headers),
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include', // support cookie-based auth later
  })
  const contentType = res.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const data = isJson ? await res.json() : await res.text()
  if (!res.ok) {
    const err = new Error((isJson && data && (data.message || data.detail)) || res.statusText)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const api = {
  // Monitoring
  getEvents: (limit = 50) => http('GET', '/events', { query: { limit } }),

  // Gate operations
  checkIn: ({ cardId, lane, plateText, vehicleType }) =>
    http('POST', '/check-in', { body: { card_id: cardId, lane, plate_text: plateText, vehicle_type: vehicleType } }),
  checkOut: ({ cardId }) => http('POST', '/check-out', { body: { card_id: cardId } }),

  // Plate updates (temporary manual fallback – requires sessionId)
  updatePlate: ({ sessionId, plateText, vehicleType }) =>
    http('POST', '/update-plate', { body: { session_id: sessionId, plate_text: plateText, vehicle_type: vehicleType } }),

  // Ask backend to start capture task
  captureTask: () => http('GET', '/capture-task'),
}

export default api


