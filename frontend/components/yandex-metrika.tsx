"use client"

import Script from "next/script"
import { usePathname, useSearchParams } from "next/navigation"
import { useEffect, Suspense } from "react"

const COUNTER_ID = 109470303

function YandexMetrikaHit() {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ym = (window as Window & { ym?: (...args: unknown[]) => void }).ym
    if (ym) ym(COUNTER_ID, "hit", window.location.href)
  }, [pathname, searchParams])

  return null
}

export function YandexMetrika() {
  return (
    <>
      <Script id="yandex-metrika" strategy="afterInteractive">
        {`
          (function(m,e,t,r,i,k,a){
            m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
            m[i].l=1*new Date();
            for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
            k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
          })(window, document,'script','https://mc.yandex.ru/metrika/tag.js', 'ym');

          ym(${COUNTER_ID}, 'init', {
            ssr: true,
            webvisor: true,
            clickmap: true,
            ecommerce: "dataLayer",
            accurateTrackBounce: true,
            trackLinks: true
          });
        `}
      </Script>
      <noscript>
        <div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`https://mc.yandex.ru/watch/${COUNTER_ID}`}
            style={{ position: "absolute", left: -9999 }}
            alt=""
          />
        </div>
      </noscript>
      <Suspense fallback={null}>
        <YandexMetrikaHit />
      </Suspense>
    </>
  )
}
