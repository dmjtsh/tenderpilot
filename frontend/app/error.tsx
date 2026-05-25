"use client"

export default function Error({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  void _error
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
      <p className="text-gray-500">Что-то пошло не так</p>
      <button
        onClick={() => reset()}
        className="px-4 py-2 text-sm font-medium bg-[#111827] text-white hover:bg-gray-800 transition-colors"
      >
        Попробовать снова
      </button>
    </div>
  )
}
