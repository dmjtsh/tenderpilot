import Link from "next/link"

const footerLinks = {
  product: {
    title: "Продукт",
    links: [
      { label: "Возможности", href: "#features" },
      { label: "Тарифы", href: "#pricing" },
      { label: "FAQ", href: "#faq" },
    ],
  },
  company: {
    title: "Компания",
    links: [
      { label: "О нас", href: "#" },
      { label: "Контакты", href: "#" },
    ],
  },
  legal: {
    title: "Юридическая информация",
    links: [
      { label: "Политика конфиденциальности", href: "/privacy" },
      { label: "Оферта", href: "/oferta" },
    ],
  },
}

export function Footer() {
  return (
    <footer className="border-t border-[#D1D5DB] bg-white">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4 lg:grid-cols-5">
          {/* Logo Column */}
          <div className="col-span-2 md:col-span-4 lg:col-span-2">
            <Link href="/" className="flex items-center gap-2">
              <img src="/logo.svg" width={28} height={28} alt="TendeRoll" />
              <span className="text-lg font-bold text-[#111827]">TendeRoll</span>
            </Link>
            <p className="mt-4 text-sm text-[#6B7280]">
              ИИ-платформа для поиска и анализа государственных закупок
            </p>
          </div>

          {/* Links Columns */}
          {Object.entries(footerLinks).map(([key, section]) => (
            <div key={key}>
              <h3 className="text-sm font-semibold text-[#111827]">{section.title}</h3>
              <ul className="mt-4 space-y-3">
                {section.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-sm text-[#6B7280] transition-colors hover:text-[#111827]"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Bar */}
        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-[#D1D5DB] pt-8 sm:flex-row">
          <div>
            <p className="text-sm text-[#6B7280]">
              {new Date().getFullYear()} TendeRoll. Все права защищены.
            </p>
            <p className="mt-1 text-xs text-[#9CA3AF]">
              Самозанятый Шутов Дмитрий Сергеевич ИНН 632136373344
            </p>
          </div>
          <p className="text-sm text-[#9CA3AF]">
            Сделано в России
          </p>
        </div>
      </div>
    </footer>
  )
}
