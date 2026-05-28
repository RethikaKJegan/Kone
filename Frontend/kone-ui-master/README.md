# SalesNXT — KONE AI Sales Visualisation Platform

SalesNXT lets KONE sales teams upload a photo of a client's building, select elevator/escalator components, have AI auto-place them onto the image, preview annotated renders, generate a video walkthrough, and export a complete client-ready sales brochure.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript + Vite 5 |
| Styling | Tailwind CSS v3 + shadcn/ui |
| State | Zustand |
| Routing | React Router v6 |
| HTTP | Axios |
| Forms | React Hook Form + Zod |
| Icons | Lucide React |
| Mock API | Vite dev-server middleware (dev only) |

---

## Getting Started

**Prerequisites:** Node.js 18+, npm 9+

```bash
npm install
npm run dev        # starts on localhost:3000 with mock API
```

### Demo credentials

These are available only when `VITE_ENABLE_MOCK_API=true`.

| Email | Password |
|---|---|
| `pavan@bellcorpstudio.com` | `password123` |
| `any@kone.com` | any non-empty password |

Or click **Continue as guest** / **View demo**. Guest login calls the Express API at `/api/v1/auth/guest-login`, receives normal auth tokens, and all project/offering actions still pass through protected backend routes and validation.

### Sign up flow

1. Go to `/signup`
2. Fill in name, email, and a password with at least 8 characters, 1 letter, and 1 number
3. Account creation is sent to the Express API so backend validation, password hashing, and token generation are applied

### Other scripts

```bash
npm run build          # production build → dist/
npm run preview        # preview the production build locally
npm run type-check     # TypeScript check without emitting
npm run lint           # ESLint
npm run test           # Vitest unit tests
npm run test:coverage  # coverage report
```

---

## Project Structure

```
src/
├── api/
│   └── client.ts                  # Axios instance + Bearer token interceptor
│
├── mocks/
│   ├── vitePlugin.ts              # Dev-only mock API (Vite server middleware)
│   └── data/
│       └── seed.ts                # In-memory Maps: users, projects, offerings, brochures
│
├── store/
│   ├── authStore.ts               # sign-in / sign-up / guest / token hydrate
│   ├── projectStore.ts            # projects CRUD
│   └── offeringStore.ts           # 6-step offering workflow + AI calls
│
├── router/
│   └── index.tsx                  # route definitions + auth guards
│
├── types/
│   └── index.ts                   # all shared TypeScript types
│
├── lib/
│   ├── utils.ts                   # cn(), formatDate(), generateId()
│   └── constants.ts               # KONE_COMPONENTS, BROCHURE_SECTIONS, AI_PLACEMENT_DEFAULTS
│
├── hooks/
│   └── useToast.ts
│
├── components/
│   ├── layout/                    # AppShell, Sidebar, TopBar
│   └── shared/                    # StepProgress, ComponentBadge, UploadZone,
│                                  # ImageCanvas, AnnotatedPreview, AIBadge, StatusBadge
│
└── pages/
    ├── landing/LandingPage.tsx
    ├── auth/                      # SignInPage, SignUpPage
    ├── projects/                  # ProjectsPage, ProjectDetailPage
    └── offering/
        ├── OfferingShell.tsx      # step progress wrapper
        ├── steps/                 # Step1Upload → Step6Download
        └── brochure/BrochurePage.tsx
```

---

## User Flow

```
/ (Landing)
  ├── /signup  →  create account  →  /projects
  ├── /signin  →  sign in         →  /projects
  └── guest    →  backend guest login → /projects
                                       │
                                  /projects/:id  (detail)
                                       │
                          /projects/:id/offerings/:id/step/1   Upload photo
                          /projects/:id/offerings/:id/step/2   Select components + environments
                          /projects/:id/offerings/:id/step/3   AI placement / manual pin
                          /projects/:id/offerings/:id/step/4   Annotated preview
                          /projects/:id/offerings/:id/step/5   Video settings
                          /projects/:id/offerings/:id/step/6   Render & download
                                       │
                          /projects/:id/offerings/:id/brochure   Sales brochure editor
```

**Route guards:**
- `/projects/*` — accessible to authenticated users and backend-authenticated guests
- All other private routes redirect to `/signin` if unauthenticated

---

## API

Development uses the Express API by default through the Vite proxy. The local mock API can still be enabled for isolated UI demos by setting `VITE_ENABLE_MOCK_API=true`.

- Default frontend base path: `/api/v1`
- Default backend target: `http://localhost:4000`
- Mock implementation: `src/mocks/vitePlugin.ts`

See [API.md](API.md) for the full endpoint reference.

---

## Design System

| Token | Value |
|---|---|
| Primary | `#0A0A0A` |
| Sidebar bg | `#0C0C0C` |
| Content bg | `#F7F7F7` |
| Card bg | `#FFFFFF` |
| Border | `#E4E4E4` |
| Border hover | `#C8C8C8` |
| Text heading | `#0A0A0A` |
| Text body | `#374151` |
| Text muted | `#A3A3A3` |
| Success | `#16A34A` |
| AI accent | `#6D28D9` (violet — AI badges only) |
| Max radius | `8px` (`rounded-lg`) |
| Font | Inter |

No blue, no gradients, no shadows heavier than `0 4px 16px rgba(0,0,0,0.08)`.

---

## License

Private — KONE Corporation internal use only.
