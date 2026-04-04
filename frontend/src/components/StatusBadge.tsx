const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  starting: 'bg-blue-100 text-blue-700',
  warming_up: 'bg-yellow-100 text-yellow-700',
  running: 'bg-indigo-100 text-indigo-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-700'
      }`}
    >
      {status}
    </span>
  )
}
