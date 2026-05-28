# Фронтенд — Next.js 14

Дата обновления: 28 мая 2026

## Стек

Next.js 14 (App Router) · React 18 · React Query v5 · Tailwind v3 · shadcn/ui · Zod · axios

## Страницы

| Маршрут | Описание |
|---------|----------|
| `/` | Лендинг (Navbar, Hero, PainPoints, Agitation, Solution, HowItWorks, Features, Stats, Pricing, FAQ, CTA, Footer) |
| `/login` | Авторизация + регистрация (табы, Zod валидация) |
| `/tenders` | Лента тендеров. Табы: "Все" / "Для вас". Фильтры, пагинация |
| `/tenders/[id]` | Детальная страница: метаданные, AI-резюме, документы, RAG чат, похожие тендеры, pipeline статус |
| `/profile` | Профиль компании: name/INN, направления (ОКВЭД, НМЦ, регионы, law types, procedure types) |
| `/pipeline` | Kanban-доска: 6 колонок, drag-drop, summary карточки, list view toggle, side panel |
| `/plan` | Биллинг: текущий план (usage bars), pricing cards с переключателем интервалов |
| `/privacy` | Политика конфиденциальности (статика) |
| `/oferta` | Оферта (статика) |

## Компоненты

### Landing (components/landing/)
| Компонент | Описание |
|-----------|----------|
| Navbar | Auth-aware, breakpoint sm, "Личный кабинет" когда авторизован |
| Hero | Staggered animate-hero, hero.png + статистика |
| PainPoints | 4 карточки проблем + скульптуры |
| Agitation | Time-waste с hourglass.png |
| Solution | Dark секция с видеоплеером, 4 факта |
| HowItWorks | 3 шага с скульптурами (quill, scales, magnifier) |
| Industries | 6 отраслевых карточек |
| Features | Left/right scroll-анимации |
| Stats | 3 стат-карточки с разделителями |
| Testimonial | Отзыв с 5 звёздами |
| Pricing | Интервал-табы, карточки standard/premium |
| FAQ | 2x2 сетка collapsible карточек |
| CTA | Скрывается когда авторизован |
| Footer | Логотип + ссылки |

### Pipeline (добавлены 25 мая)
| Компонент | Описание |
|-----------|----------|
| PipelineSidePanel | 600px right-slide panel с табами: Overview/AI/Docs/Comments/Activity |
| PipelineAiSummary | AI резюме в side panel |
| PipelineChat | RAG чат в side panel |
| PipelineComments | Комментарии |
| PipelineActivity | Timeline активности |
| PipelineListView | Табличный вид (альтернатива kanban) |
| PipelineStatusButtons | 6 кнопок статусов на странице тендера |

### Filters (components/filters/)
- filter-bar, filter-dropdown, multi-select-filter, range-filter, deadline-filter

### Top-level
- Shell — sidebar layout, mobile hamburger
- Nav — простой top navbar (authenticated only)
- TenderCard — карточка тендера (score %, b2b badge, НМЦК, deadline)
- OkvedCombobox — поиск ОКВЭД, 20 популярных presets
- ProfilePricing — pricing cards для /plan

## Дизайн-система

### Приложение (Linear.app стиль)
```
Background:  white / gray-50
Cards:       white, border gray-200
Accent:      violet-600 (#7C3AED)
Text:        gray-900 primary, gray-500 secondary
Direction buttons: bg-violet-100 border-violet-300 text-violet-800
"Все" button: bg-[#111827] text-white
```

### Лендинг (Stripe/Minerva стиль)
```
Background:  white
Cards:       gray-50, border gray-200
Accent:      black (#111827) для кнопок
Highlight:   violet-600 — только акценты
```

**Тема только светлая** — не менять на тёмную ни для лендинга, ни для приложения.

## CSS Анимации (globals.css)

- `scroll-hidden / scroll-visible` — fade-up при скролле (24px, 0.6s)
- `scroll-hidden-left / scroll-hidden-right` — directional slide-in (32px)
- `scroll-hidden-scale` — scale-up (0.95→1)
- `.stagger-1..6` — каскадные задержки (0-500ms)
- `.animate-hero` — entrance для hero секции
- `.btn-hover-lift` — подъём кнопок при hover
- `.info-html-content` — стили для info_html таблиц/ссылок
- `@media (prefers-reduced-motion: reduce)` — accessibility
- Глобальный `cursor: pointer` для button/a (Tailwind v3 preflight fix)

## Ключевые паттерны

- `useState(() => new QueryClient())` в providers.tsx — намеренно
- `mounted` state в Shell.tsx — hydration fix
- 401 interceptor только при наличии токена
- Таб "Для вас" персистится в URL (`?tab=match`)
- React Query v5: `isLoading = isPending && isFetching`
- DRF ListCreateAPIView: `r.data.results ?? r.data`
- DocumentsBlock и AiSummaryBlock: один React Query ключ для /docs/

## API Types (lib/api.ts)

Все TypeScript интерфейсы соответствуют бэкенд моделям.
Ключевые: Tender, TenderSummaryV2, TenderDoc, CompanyDirection, UserPlan, TenderPipelineEntry, PipelineComment, PipelineActivityEntry, PipelineSummary

## Зависимости

next 14, react 18, @tanstack/react-query 5, react-hook-form 7, zod 4, axios 1.15, lucide-react, @hello-pangea/dnd (kanban drag-drop), cmdk (combobox), shadcn 4, tailwind-merge, CVA
