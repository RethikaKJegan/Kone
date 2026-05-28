# SalesNXT — API Reference

The UI is wired to the Express API by default. The Vite dev-server mock (`src/mocks/vitePlugin.ts`) is available only when `VITE_ENABLE_MOCK_API=true`.  
Base path: `/api/v1` in the UI, proxied to `http://localhost:4000` during development.  
Auth: `Authorization: Bearer <token>` header on all protected routes.

---

## Auth

### `POST /api/v1/auth/register`

Create a new account.

**Request**
```json
{
  "name": "Pavan Kumar",
  "email": "pavan@example.com",
  "password": "mysecurepassword"
}
```

**Validation**
- `name` — min 2 characters
- `email` — valid email format
- `password` — min 8 characters, at least 1 letter, at least 1 number

**Response `201`**
```json
{
  "user": {
    "id": "user-1718000000000-abc1234",
    "email": "pavan@example.com",
    "name": "Pavan Kumar",
    "role": "authenticated",
    "company": "KONE",
    "avatarInitials": "PK"
  },
  "tokens": {
    "access": {
      "token": "jwt-access-token",
      "expires": "2026-05-28T10:30:00.000Z"
    },
    "refresh": {
      "token": "jwt-refresh-token",
      "expires": "2026-06-27T10:00:00.000Z"
    }
  }
}
```

**Error `400`** — email already registered
```json
{ "message": "An account with this email already exists" }
```

**Error `400`** — password too short
```json
{ "message": "Password must be at least 8 characters" }
```

---

### `POST /api/v1/auth/login`

Sign in with existing credentials.

**Request**
```json
{
  "email": "pavan@example.com",
  "password": "mysecurepassword"
}
```

**Response `200`** — same shape as signup `201`

**Error `401`** — wrong credentials
```json
{ "message": "Incorrect email or password" }
```

---

### `POST /api/v1/auth/logout`

Invalidate the current session.

**Response `200`**
```json
{ "message": "Signed out" }
```

---

### `POST /api/v1/auth/guest-login`

Create a temporary guest session with normal access and refresh tokens.

**Response `201`**
```json
{
  "user": {
    "id": "guest-user-id",
    "email": "guest-...@salesnxt.local",
    "name": "Guest User",
    "role": "guest",
    "company": "KONE",
    "avatarInitials": "GU"
  },
  "tokens": {
    "access": { "token": "jwt-access-token", "expires": "2026-05-28T10:30:00.000Z" },
    "refresh": { "token": "jwt-refresh-token", "expires": "2026-06-27T10:00:00.000Z" }
  }
}
```

Guest project, offering, brochure, and video actions use the same protected API routes as signed-in users.

---

### `GET /api/v1/auth/me`

Return the user for the current token.

**Headers:** `Authorization: Bearer <token>`

**Response `200`** — `User` object (same as signup response, minus token)

**Error `401`**
```json
{ "message": "Unauthorized" }
```

---

## Projects

### `GET /api/v1/projects`

List all projects for the authenticated user.

**Headers:** `Authorization: Bearer <token>`

**Response `200`**
```json
[
  {
    "id": "proj-1",
    "name": "Dubai Tower",
    "status": "draft",
    "createdAt": "2026-05-21T00:00:00.000Z",
    "updatedAt": "2026-05-21T00:00:00.000Z",
    "offeringCount": 0,
    "userId": "user-1"
  }
]
```

---

### `POST /api/v1/projects`

Create a new project.

**Request**
```json
{ "name": "Dubai Tower" }
```

**Validation:** name 2–80 characters

**Response `201`** — full `Project` object

**Error `400`**
```json
{ "message": "Project name must be 2–80 characters" }
```

---

### `DELETE /api/v1/projects/:id`

Delete a project by ID.

**Response `204`** — no body

---

## Offerings

### `GET /api/v1/projects/:projectId/offerings`

List all offerings for a project.

**Response `200`** — array of `Offering` objects

---

### `POST /api/v1/projects/:projectId/offerings`

Create a new offering (always starts as draft with all defaults).

**Response `201`**
```json
{
  "id": "off-1718000000000-abc1234",
  "projectId": "proj-1",
  "name": "Offering 1",
  "status": "draft",
  "createdAt": "2026-05-22T00:00:00.000Z",
  "uploadedFileUrl": null,
  "uploadedFileName": null,
  "uploadedFileType": null,
  "environments": [],
  "selectedComponents": [],
  "componentPins": [],
  "annotationsEnabled": true,
  "activeAnnotationFilters": [],
  "videoMotionStyle": "zoom-in",
  "videoSpeed": 1,
  "videoQuality": "1080p",
  "renderComplete": false
}
```

---

### `PATCH /api/offerings/:id`

Partial update of any offering fields. Used by every workflow step.

**Request** — any subset of `Offering` fields:
```json
{
  "uploadedFileUrl": "blob:http://localhost:3000/...",
  "uploadedFileName": "building.jpg",
  "uploadedFileType": "image"
}
```

Or for components step:
```json
{
  "environments": ["car", "lobby"],
  "selectedComponents": ["ceiling", "lci", "door", "cop"],
  "componentPins": [],
  "activeAnnotationFilters": ["ceiling", "lci", "door", "cop"]
}
```

Or for video settings:
```json
{
  "videoMotionStyle": "pan-lr",
  "videoSpeed": 1.5,
  "videoQuality": "1080p"
}
```

**Response `200`** — full updated `Offering` object

**Error `404`**
```json
{ "message": "Not found" }
```

---

### `POST /api/offerings/:id/ai-placement`

Trigger AI component placement. Returns pin coordinates as percentage of image dimensions.

**Simulated delay:** 1800 ms

**Response `200`** — array of `ComponentPin` for each selected component:
```json
[
  { "componentKey": "ceiling", "x": 50, "y": 10, "aiPlaced": true },
  { "componentKey": "lci",     "x": 78, "y": 40, "aiPlaced": true },
  { "componentKey": "door",    "x": 20, "y": 55, "aiPlaced": true },
  { "componentKey": "cop",     "x": 18, "y": 52, "aiPlaced": true }
]
```

Only pins for the offering's `selectedComponents` are returned.

**Error `404`**
```json
{ "message": "Not found" }
```

---

### `POST /api/offerings/:id/render`

Trigger composite render + video generation. Updates `renderComplete: true`.

**Simulated delay:** 2200 ms

**Response `200`** — full updated `Offering` object with `"renderComplete": true`

---

### `POST /api/offerings/:id/complete`

Mark an offering as complete (end of step 6).

**Response `200`** — full updated `Offering` object with `"status": "complete"`

---

## Brochure

### `GET /api/offerings/:offeringId/brochure`

Fetch the brochure for an offering.

**Response `200`**
```json
{
  "id": "brochure-1718000000000-abc1234",
  "offeringId": "off-1",
  "projectId": "proj-1",
  "content": {
    "offeringOverview": "",
    "competitorComparison": "",
    "uniqueSellingPoints": "",
    "customerBenefits": "",
    "additionalNotes": ""
  },
  "tenderPdfUrl": null,
  "sectionsComplete": 0,
  "createdAt": "2026-05-22T00:00:00.000Z"
}
```

**Error `404`** — not yet created

---

### `POST /api/offerings/:offeringId/brochure`

Create a brochure for an offering. Idempotent — returns existing brochure if one already exists.

**Request**
```json
{ "projectId": "proj-1" }
```

**Response `201`** — `Brochure` object with empty content

---

### `PATCH /api/offerings/:offeringId/brochure`

Update one or more brochure sections. Automatically recalculates `sectionsComplete`.

**Request**
```json
{
  "content": {
    "offeringOverview": "KONE MonoSpace 500 for a 12-floor commercial tower..."
  }
}
```

**Response `200`** — full updated `Brochure` object. `sectionsComplete` is the count of non-empty sections (max 5).

---

## Data Types

```typescript
type UserRole = 'authenticated'

interface User {
  id: string
  email: string
  name: string
  role: UserRole
  company: string
  avatarInitials: string   // 2 uppercase letters
}

type ProjectStatus = 'draft' | 'active' | 'complete'

interface Project {
  id: string
  name: string
  status: ProjectStatus
  createdAt: string        // ISO 8601
  updatedAt: string
  offeringCount: number
  userId: string
}

type Environment  = 'car' | 'lobby'
type ComponentKey = 'ceiling' | 'lci' | 'door' | 'cop'

interface ComponentPin {
  componentKey: ComponentKey
  x: number                // % of image width  (0–100)
  y: number                // % of image height (0–100)
  aiPlaced: boolean
}

type OfferingStatus = 'draft' | 'complete'

interface Offering {
  id: string
  projectId: string
  name: string
  status: OfferingStatus
  createdAt: string
  uploadedFileUrl: string | null
  uploadedFileName: string | null
  uploadedFileType: 'image' | 'video' | null
  environments: Environment[]
  selectedComponents: ComponentKey[]
  componentPins: ComponentPin[]
  annotationsEnabled: boolean
  activeAnnotationFilters: ComponentKey[]
  videoMotionStyle: 'zoom-in' | 'pan-lr' | 'pan-rl'
  videoSpeed: 0.5 | 1 | 1.5
  videoQuality: '360p' | '480p' | '720p' | '1080p'
  renderComplete: boolean
}

interface BrochureContent {
  offeringOverview: string
  competitorComparison: string
  uniqueSellingPoints: string
  customerBenefits: string
  additionalNotes: string
}

interface Brochure {
  id: string
  offeringId: string
  projectId: string
  content: BrochureContent
  tenderPdfUrl: string | null
  sectionsComplete: number   // 0–5
  createdAt: string
}
```

---

## Real API Requirements (when backend is built)

The table below describes what each endpoint needs in production.

| Endpoint | What it needs |
|---|---|
| `POST /api/v1/auth/register` | User table in DB, password hashing (bcrypt), JWT signing |
| `POST /api/v1/auth/login` | Password verify (bcrypt), JWT signing |
| `GET /api/v1/auth/me` | JWT verify, user lookup |
| `POST /api/v1/auth/logout` | Refresh token invalidation |
| `GET/POST/DELETE /api/v1/projects` | Projects table scoped to `userId` |
| `GET/POST /api/v1/projects/:id/offerings` | Offerings table with `projectId` FK |
| `PATCH /api/offerings/:id` | Generic partial update |
| `POST /api/offerings/:id/ai-placement` | **Vision model** (GPT-4o / Gemini Vision) — detect surfaces in uploaded photo, return `{x, y}` percentages per component |
| `POST /api/offerings/:id/render` | **Image compositing** (Sharp / Pillow) — overlay component PNGs at pin coords; **Video generation** (FFmpeg) |
| `POST /api/offerings/:id/complete` | Status update |
| `GET/POST/PATCH /api/offerings/:id/brochure` | Brochure table, content stored as JSON column |
| File upload _(not yet wired)_ | `POST /api/uploads` → S3 / Azure Blob, return permanent CDN URL. Currently uses `URL.createObjectURL` which is browser-local and lost on refresh |
| PDF export _(stub)_ | `POST /api/offerings/:id/export/pdf` → Puppeteer / WeasyPrint |
| PPT export _(stub)_ | `POST /api/offerings/:id/export/ppt` → python-pptx / officegen |

---

## Mock-Specific Behaviour

| Behaviour | Detail |
|---|---|
| State lifetime | In-memory `Map` objects live for the dev server process session. Seeded data always resets on restart. |
| New signups | Persist for the session — you can sign out and sign back in with new credentials until the dev server restarts. |
| Simulated latency | Auth: 600–700 ms · CRUD: 300–500 ms · AI placement: 1800 ms · Render: 2200 ms |
| `@kone.com` emails | Any `@kone.com` address with a non-empty password signs in without a prior signup |
| Seeded data | `pavan@bellcorpstudio.com` / `password123` always present; 2 seeded projects (Dubai Tower, Helsinki HQ); 1 seeded complete offering |
