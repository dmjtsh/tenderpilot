"use client"

import { Star } from "lucide-react"
import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

export function Testimonial() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section className="bg-[#F3F4F6] py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <div className={`relative text-center scroll-hidden-scale ${isVisible ? "scroll-visible" : ""}`}>
          <div className="absolute -top-4 left-1/2 -translate-x-1/2 font-serif text-8xl leading-none text-[#D1D5DB]">
            &ldquo;
          </div>

          <blockquote className="relative pt-12">
            <p className="text-xl leading-relaxed text-[#111827] sm:text-2xl">
              За первый месяц нашли 3 тендера которые раньше пропускали.
              Один выиграли на 8.4 млн ₽, окупили подписку в 200 раз.
            </p>

            <footer className="mt-8">
              <div className="flex items-center justify-center gap-1">
                {[...Array(5)].map((_, i) => (
                  <Star
                    key={i}
                    className="h-5 w-5 fill-[#111827] text-[#111827]"
                  />
                ))}
              </div>
              <div className="mt-6 flex items-center justify-center gap-4">
                <Image
                  src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=64&h=64&fit=crop&crop=face"
                  alt="Фото клиента"
                  width={48}
                  height={48}
                  className="border border-[#D1D5DB]"
                />
                <div className="text-left">
                  <span className="block font-medium text-[#111827]">
                    Директор по развитию
                  </span>
                  <span className="text-sm text-[#6B7280]">строительная компания, Самара</span>
                </div>
              </div>
            </footer>
          </blockquote>
        </div>
      </div>
    </section>
  )
}
