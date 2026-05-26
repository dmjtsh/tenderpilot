"use client"

import { useRef, useState } from "react"
import { Play } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

export function DemoVideo() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const { ref, isVisible } = useScrollAnimation()

  function handlePlay() {
    const video = videoRef.current
    if (!video) return
    setPlaying(true)
    video.play()
  }

  function handleVideoClick() {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play()
    } else {
      video.pause()
    }
  }

  return (
    <section id="demo" className="bg-[#FAFAFA] py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`text-center scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Посмотрите, как это работает
          </h2>
          <p className="mt-4 text-lg text-[#6B7280]">
            2 минуты — и вы поймёте, зачем это нужно вашей команде
          </p>
        </div>

        <div
          className={`mt-12 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}
          style={{ transitionDelay: "0.15s" }}
        >
          <div className="relative mx-auto max-w-4xl overflow-hidden rounded-2xl shadow-2xl border border-gray-200">
            <video
              ref={videoRef}
              src="/demo.mp4"
              preload="none"
              poster="/demo-poster.jpg"
              className="w-full aspect-video bg-[#111827] cursor-pointer"
              onClick={handleVideoClick}
              onEnded={() => setPlaying(false)}
              controls={playing}
              playsInline
            />

            {!playing && (
              <button
                onClick={handlePlay}
                aria-label="Смотреть демо"
                className="absolute inset-0 flex items-center justify-center bg-black/30 transition-opacity hover:bg-black/40 group"
              >
                <span className="flex h-20 w-20 items-center justify-center rounded-full bg-white shadow-lg transition-transform group-hover:scale-110">
                  <Play className="h-8 w-8 translate-x-0.5 text-[#111827]" fill="#111827" />
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
