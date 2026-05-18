import { Navbar } from "@/components/landing/navbar"
import { Hero } from "@/components/landing/hero"
import { PainPoints } from "@/components/landing/pain-points"
import { Agitation } from "@/components/landing/agitation"
import { Solution } from "@/components/landing/solution"
import { HowItWorks } from "@/components/landing/how-it-works"
import { Pricing } from "@/components/landing/pricing"
import { FAQ } from "@/components/landing/faq"
import { CTA } from "@/components/landing/cta"
import { Footer } from "@/components/landing/footer"

const jsonLdApp = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "ТендерПилот",
  url: "https://pilot-tender.ru",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "ИИ для тендеров: автоматизация поиска госзакупок по 44-ФЗ, 223-ФЗ и 615-ПП. ИИ-поиск тендеров, ИИ-анализ документации, помощник тендериста.",
  offers: {
    "@type": "AggregateOffer",
    priceCurrency: "RUB",
    lowPrice: "0",
    highPrice: "6990",
    offerCount: "3",
  },
}

const jsonLdFaq = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "Какие площадки охватывает ТендерПилот?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Все федеральные площадки госзакупок: ЕИС, Сбербанк-АСТ, РТС-Тендер, Росэлторг, Фабрикант. Поддерживаем закупки по 44-ФЗ, 223-ФЗ и 615-ПП. Также работаем с B2B-площадками: Бидзаар, B2B-Center, ОТС.Маркет.",
      },
    },
    {
      "@type": "Question",
      name: "Насколько точно ИИ подбирает тендеры?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Мы используем семантический поиск, а не простое совпадение по ключевым словам. Вы настраиваете направления с ОКВЭД, регионами и диапазоном НМЦК, и система подбирает тендеры по смыслу вашей деятельности. Чем точнее заполнен профиль, тем релевантнее подборка.",
      },
    },
    {
      "@type": "Question",
      name: "Что если ИИ ошибётся в анализе документов?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "AI-резюме это помощник, а не замена юристу. Мы всегда показываем источник: каждый факт в резюме можно проверить через чат с тендером, который даёт ответ с цитатой из конкретного документа. Финальное решение всегда за вами.",
      },
    },
    {
      "@type": "Question",
      name: "Безопасно ли загружать данные в ТендерПилот?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Мы не запрашиваем конфиденциальные данные вашей компании. Профиль содержит только открытую информацию: ИНН, направления деятельности, регионы. Документы тендеров это публичная информация с площадок госзакупок.",
      },
    },
    {
      "@type": "Question",
      name: "Как найти тендер по 44-ФЗ?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "В ТендерПилоте тендеры по 44-ФЗ обновляются каждый час напрямую из ЕИС (zakupki.gov.ru). Укажите ОКВЭД-коды, регион и диапазон НМЦК в профиле, и система автоматически подберёт релевантные закупки. Также доступен свободный семантический поиск по ключевым словам.",
      },
    },
    {
      "@type": "Question",
      name: "Чем ТендерПилот отличается от поиска на zakupki.gov.ru?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "На ЕИС поиск работает по точному совпадению ключевых слов. ТендерПилот использует семантический ИИ-поиск, который понимает смысл запроса. Плюс автоматический подбор под профиль компании, AI-резюме документации за 10 секунд и чат с тендером для быстрых ответов по документам.",
      },
    },
    {
      "@type": "Question",
      name: "Сколько стоит сервис для поиска тендеров?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Бесплатный тариф включает подбор тендеров, 2 AI-резюме и 10 вопросов к документам в день. Платные тарифы от 2 990 руб/мес с увеличенными лимитами. Enterprise — по договорённости с API-доступом и персональным менеджером.",
      },
    },
    {
      "@type": "Question",
      name: "Как автоматизировать поиск тендеров?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Заполните профиль компании: укажите ИНН, направления деятельности с ОКВЭД-кодами, регионы и ценовой диапазон. ТендерПилот будет автоматически подбирать тендеры под каждое направление. Новые закупки появляются в ленте каждый час.",
      },
    },
    {
      "@type": "Question",
      name: "Можно ли использовать ИИ для анализа тендерной документации?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Да. ТендерПилот генерирует AI-резюме по всей документации тендера за 10 секунд: суть работ, условия оплаты, штрафы, обеспечение, требования к участникам. Также можно задать любой вопрос по документам в чате и получить ответ с цитатой из конкретного документа.",
      },
    },
    {
      "@type": "Question",
      name: "Какие тендеры можно найти в ТендерПилоте?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Все госзакупки по 44-ФЗ и 223-ФЗ из Единой информационной системы (ЕИС). Электронные аукционы, конкурсы, запросы котировок, запросы предложений и закупки у единственного поставщика. База обновляется каждый час и содержит более 130 000 тендеров.",
      },
    },
    {
      "@type": "Question",
      name: "Подходит ли ТендерПилот для малого бизнеса и ИП?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Да, платформа создана в первую очередь для малого и среднего бизнеса. Бесплатный тариф позволяет оценить подбор тендеров без вложений. Автоматический мониторинг экономит часы ручного поиска, что критично для небольших команд где тендерами занимается один человек.",
      },
    },
    {
      "@type": "Question",
      name: "Что такое семантический поиск тендеров?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Классический поиск ищет точное совпадение слов. Семантический поиск понимает смысл: запрос «ремонт кровли» найдёт тендеры на «восстановление кровельного покрытия», «замена гидроизоляции крыши» и другие по смыслу подходящие закупки, даже если точных слов нет в названии.",
      },
    },
    {
      "@type": "Question",
      name: "Как отслеживать статус участия в тендерах?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "В ТендерПилоте есть Pipeline — kanban-доска для отслеживания тендеров по этапам: новый, изучаю, готовлю заявку, подал, выиграл, проиграл. Видите всю воронку участия и сумму тендеров в работе.",
      },
    },
    {
      "@type": "Question",
      name: "Нужна ли электронная подпись для работы с ТендерПилотом?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Нет, для работы с ТендерПилотом электронная подпись не нужна. Сервис помогает найти и проанализировать тендеры. Электронная подпись потребуется только для подачи заявки непосредственно на торговой площадке.",
      },
    },
  ],
}

const jsonLdOrg = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "ТендерПилот",
  url: "https://pilot-tender.ru",
  logo: "https://pilot-tender.ru/logo.png",
  description:
    "ИИ-платформа для автоматического поиска тендеров и госзакупок в России",
  foundingDate: "2025",
  areaServed: { "@type": "Country", name: "Россия" },
}

export default function Home() {
  return (
    <main className="min-h-screen bg-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdApp) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdFaq) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdOrg) }}
      />
      <Navbar />
      <Hero />
      <PainPoints />
      <Agitation />
      <Solution />
      <HowItWorks />
      <Pricing />
      <FAQ />
      <CTA />
      <Footer />
    </main>
  )
}
