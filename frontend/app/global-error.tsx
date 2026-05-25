"use client"

export default function GlobalError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  void _error
  return (
    <html>
      <body>
        <div style={{ padding: 40, textAlign: "center" }}>
          <h2>Произошла ошибка</h2>
          <button onClick={() => reset()} style={{ marginTop: 16, padding: "8px 16px" }}>
            Попробовать снова
          </button>
        </div>
      </body>
    </html>
  )
}
