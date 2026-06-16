const COLORS = {
  delivered:           'bg-green-100 text-green-800',
  departed:            'bg-blue-100 text-blue-800',
  in_transit:          'bg-blue-100 text-blue-800',
  arrived:             'bg-teal-100 text-teal-800',
  in_origin_terminal:  'bg-indigo-100 text-indigo-800',
  received:            'bg-indigo-100 text-indigo-800',
  customs:             'bg-yellow-100 text-yellow-800',
  ready_for_pickup:    'bg-yellow-100 text-yellow-800',
  container_picked_up: 'bg-purple-100 text-purple-800',
  container_returned:  'bg-purple-100 text-purple-800',
  exception:           'bg-red-100 text-red-800',
  not_found:           'bg-gray-100 text-gray-500',
  unknown:             'bg-gray-100 text-gray-500',
}

export default function StatusBadge({ status, label }) {
  const color = COLORS[status] || 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label || status || '—'}
    </span>
  )
}
