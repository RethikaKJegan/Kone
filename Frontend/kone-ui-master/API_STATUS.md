# API Integration Status

Backend base URL: `http://localhost:4000/api/v1`  
Frontend base URL config: `VITE_API_BASE_URL` in `.env.development`

Legend: ✅ Integrated · ❌ Not integrated · 🔒 Admin only

---

## Auth — `/api/v1/auth`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| POST | `/auth/register` | ✅ | `authStore.signUp()` |
| POST | `/auth/login` | ✅ | `authStore.signIn()` |
| POST | `/auth/logout` | ✅ | `authStore.signOut()` — sends refresh token |
| POST | `/auth/refresh-tokens` | ❌ | Access tokens expire silently; no auto-refresh logic |
| POST | `/auth/forgot-password` | ❌ | No forgot-password UI page |
| POST | `/auth/reset-password` | ❌ | No reset-password UI page |
| POST | `/auth/send-verification-email` | ❌ | Email verification not triggered from UI |
| POST | `/auth/verify-email` | ❌ | No verify-email callback page |

---

## Users — `/api/v1/users`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/users` | ❌ 🔒 | Admin-only; no admin panel in UI |
| POST | `/users` | ❌ 🔒 | Admin-only; no admin panel in UI |
| GET | `/users/:userId` | ❌ | No user profile page |
| PATCH | `/users/:userId` | ❌ | No account settings page |
| DELETE | `/users/:userId` | ❌ | No account deletion flow |

---

## Video Pipeline — `/api/v1/video`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| POST | `/video/upload-image` | ✅ | `offeringStore.setUpload()` — multipart upload, stores `imageId` |
| POST | `/video/select-environment` | ✅ | `offeringStore.setComponents()` — fire-and-forget |
| POST | `/video/select-components` | ✅ | `offeringStore.setComponents()` — fire-and-forget |
| POST | `/video/generate` | ✅ | `offeringStore.triggerRender()` — called before marking render complete |

---

## Projects — `/api/v1/projects`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/projects` | ✅ | `projectStore.fetchProjects()` |
| POST | `/projects` | ✅ | `projectStore.createProject()` |
| DELETE | `/projects/:projectId` | ✅ | `projectStore.deleteProject()` |
| GET | `/projects/:projectId/offerings` | ✅ | `offeringStore.fetchOfferings()` |
| POST | `/projects/:projectId/offerings` | ✅ | `offeringStore.createOffering()` |

---

## Offerings — `/api/v1/offerings`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| PATCH | `/offerings/:offeringId` | ✅ | Called by `setUpload`, `setComponents`, `setPins`, `setAnnotationState`, `setVideoSettings` |
| POST | `/offerings/:offeringId/ai-placement` | ✅ | `offeringStore.runAIPlacement()` |
| POST | `/offerings/:offeringId/render` | ✅ | `offeringStore.triggerRender()` |
| POST | `/offerings/:offeringId/complete` | ✅ | `offeringStore.completeOffering()` |

---

## Brochure — `/api/v1/offerings/:offeringId/brochure`

| Method | Endpoint | Status | Notes |
|--------|----------|--------|-------|
| GET | `/offerings/:offeringId/brochure` | ✅ | `BrochurePage.tsx` — fetches on mount |
| POST | `/offerings/:offeringId/brochure` | ✅ | `BrochurePage.tsx` — creates if GET returns 404 |
| PATCH | `/offerings/:offeringId/brochure` | ✅ | `BrochurePage.tsx` — `handleSectionSave()` |

---

## Summary

| Category | Total | Integrated | Not Integrated |
|----------|-------|------------|----------------|
| Auth | 8 | 3 | 5 |
| Users | 5 | 0 | 5 |
| Video Pipeline | 4 | 4 | 0 |
| Projects | 5 | 5 | 0 |
| Offerings | 4 | 4 | 0 |
| Brochure | 3 | 3 | 0 |
| **Total** | **29** | **19** | **10** |

---

## Pending Integration

### Auth flows (need UI pages)
- **Forgot password** — requires `/forgot-password` route + form that calls `POST /auth/forgot-password`
- **Reset password** — requires `/reset-password?token=...` route + form that calls `POST /auth/reset-password`
- **Email verification** — requires `POST /auth/send-verification-email` trigger post-signup + `/verify-email?token=...` callback route
- **Token refresh** — requires a response interceptor in `src/api/client.ts` that catches 401s and calls `POST /auth/refresh-tokens` using the stored refresh token, then retries the original request

### User management (need UI pages)
- **Profile / account settings** — `GET` + `PATCH /users/:userId` (name, email, password)
- **Account deletion** — `DELETE /users/:userId`
- **Admin panel** — `GET` + `POST /users` (admin-only, guarded by `role === 'admin'`)
