import { ImageResponse } from "next/og"

export const runtime = "edge"
export const alt = "TendeRoll — автоматизация поиска тендеров и госзакупок"
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#111827",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "60px",
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 700,
            color: "#ffffff",
            marginBottom: 24,
            letterSpacing: "-0.02em",
          }}
        >
          TendeRoll
        </div>
        <div
          style={{
            fontSize: 32,
            color: "#9CA3AF",
            textAlign: "center",
            maxWidth: 800,
            lineHeight: 1.4,
          }}
        >
          ИИ-поиск и анализ тендеров
        </div>
        <div
          style={{
            display: "flex",
            gap: 32,
            marginTop: 48,
          }}
        >
          {["ИИ-подбор тендеров", "ИИ-анализ документов", "Помощник тендериста"].map((t) => (
            <div
              key={t}
              style={{
                fontSize: 20,
                color: "#7C3AED",
                border: "1px solid #7C3AED",
                borderRadius: 8,
                padding: "8px 20px",
              }}
            >
              {t}
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size }
  )
}
