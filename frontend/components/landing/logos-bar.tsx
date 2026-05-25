export function LogosBar() {
  return (
    <section className="border-y border-[#E5E7EB] bg-white py-12">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <p className="text-center text-sm text-[#9CA3AF]">
          Компании которые уже используют TendeRoll:
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-12 gap-y-6">
          {/* Placeholder company logos */}
          {["СтройГрупп", "МедТех", "ИнфоСистемы", "ТехноПром", "ГрадСтрой", "СервисПро"].map((name) => (
            <div key={name} className="text-lg font-semibold text-[#D1D5DB]">
              {name}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
