import type { Plugin } from 'vite'
import type { IncomingMessage, ServerResponse } from 'node:http'
import {
  users,
  tokens,
  projects,
  offerings,
  brochures,
  createProject,
  createOffering,
  getUserFromToken,
} from './data/seed'
import { generateId, initials as getInitials } from '../lib/utils'
import { AI_PLACEMENT_DEFAULTS } from '../lib/constants'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
  })
}

function send(res: ServerResponse, data: unknown, status = 200): void {
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.statusCode = status
  res.end(JSON.stringify(data))
}

function matchPath(pattern: string, urlPath: string): Record<string, string> | null {
  const pp = pattern.split('/')
  const up = urlPath.split('/')
  if (pp.length !== up.length) return null
  const params: Record<string, string> = {}
  for (let i = 0; i < pp.length; i++) {
    if (pp[i].startsWith(':')) {
      params[pp[i].slice(1)] = decodeURIComponent(up[i])
    } else if (pp[i] !== up[i]) {
      return null
    }
  }
  return params
}

function makeTokenPair(userId: string) {
  const accessToken = generateId()
  const refreshToken = generateId()
  tokens.set(accessToken, userId)
  return {
    access: { token: accessToken, expires: new Date(Date.now() + 30 * 60 * 1000).toISOString() },
    refresh: { token: refreshToken, expires: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() },
  }
}

export function mockApiPlugin(): Plugin {
  return {
    name: 'mock-api',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(async (req: IncomingMessage, res: ServerResponse, next: () => void) => {
        const rawUrl = req.url ?? ''
        const urlPath = rawUrl.split('?')[0]
        const method = (req.method ?? 'GET').toUpperCase()

        if (!urlPath.startsWith('/api/')) return next()

        // Handle CORS preflight
        if (method === 'OPTIONS') {
          res.setHeader('Access-Control-Allow-Origin', '*')
          res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,DELETE,OPTIONS')
          res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization')
          res.statusCode = 204
          res.end()
          return
        }

        try {
          // ── AUTH ────────────────────────────────────────────────────────

          if (method === 'POST' && urlPath === '/api/v1/auth/login') {
            await sleep(600)
            const body = JSON.parse(await readBody(req)) as { email: string; password: string }
            const userRecord = users.get(body.email)
            const isKoneEmail = body.email.endsWith('@kone.com') && body.password.length > 0

            if (!userRecord && !isKoneEmail) {
              return send(res, { code: 400, message: 'Incorrect email or password' }, 400)
            }
            if (userRecord && userRecord.password !== body.password) {
              return send(res, { code: 400, message: 'Incorrect email or password' }, 400)
            }

            let user
            if (userRecord) {
              const { password: _p, ...rest } = userRecord
              user = rest
            } else {
              const raw = body.email.split('@')[0].replace('.', ' ')
              const name = raw.charAt(0).toUpperCase() + raw.slice(1)
              user = {
                id: `user-${generateId()}`,
                email: body.email,
                name,
                role: 'authenticated' as const,
                company: 'KONE',
                avatarInitials: getInitials(name),
              }
            }
            const mockTokens = makeTokenPair(user.id)
            return send(res, { user, tokens: mockTokens })
          }

          if (method === 'POST' && urlPath === '/api/v1/auth/register') {
            await sleep(700)
            const body = JSON.parse(await readBody(req)) as {
              name: string
              email: string
              password: string
            }
            if (users.has(body.email)) {
              return send(res, { code: 400, message: 'Email already taken' }, 400)
            }
            if (body.password.length < 8) {
              return send(res, { code: 400, message: 'Password must be at least 8 characters' }, 400)
            }
            const user = {
              id: `user-${generateId()}`,
              email: body.email,
              name: body.name,
              role: 'authenticated' as const,
              company: 'KONE',
              avatarInitials: getInitials(body.name),
            }
            users.set(body.email, { ...user, password: body.password })
            const mockTokens = makeTokenPair(user.id)
            return send(res, { user, tokens: mockTokens }, 201)
          }

          if (method === 'POST' && urlPath === '/api/v1/auth/logout') {
            res.statusCode = 204
            res.end()
            return
          }

          if (method === 'GET' && urlPath === '/api/v1/auth/me') {
            const auth = (req.headers['authorization'] as string | undefined) ?? null
            const user = getUserFromToken(auth)
            if (!user) return send(res, { code: 401, message: 'Unauthorized' }, 401)
            return send(res, user)
          }

          // ── PROJECTS ────────────────────────────────────────────────────

          if (method === 'GET' && urlPath === '/api/v1/projects') {
            await sleep(400)
            const auth = (req.headers['authorization'] as string | undefined) ?? null
            const user = getUserFromToken(auth)
            if (!user) return send(res, [])
            const list = [...projects.values()].filter((p) => p.userId === user.id)
            return send(res, list)
          }

          if (method === 'POST' && urlPath === '/api/v1/projects') {
            await sleep(500)
            const auth = (req.headers['authorization'] as string | undefined) ?? null
            const user = getUserFromToken(auth)
            const body = JSON.parse(await readBody(req)) as { name: string }
            if (!body.name || body.name.length < 2 || body.name.length > 80) {
              return send(res, { code: 400, message: 'Project name must be 2–80 characters' }, 400)
            }
            const userId = user?.id ?? `guest-${Date.now()}`
            const project = createProject(body.name, userId)
            return send(res, project, 201)
          }

          const deleteP = matchPath('/api/v1/projects/:id', urlPath)
          if (method === 'DELETE' && deleteP) {
            await sleep(300)
            projects.delete(deleteP.id)
            res.statusCode = 204
            res.end()
            return
          }

          // ── OFFERINGS ───────────────────────────────────────────────────

          const offeringsRoute = matchPath('/api/v1/projects/:projectId/offerings', urlPath)
          if (offeringsRoute) {
            if (method === 'GET') {
              await sleep(350)
              const list = [...offerings.values()].filter(
                (o) => o.projectId === offeringsRoute.projectId
              )
              return send(res, list)
            }
            if (method === 'POST') {
              await sleep(400)
              const offering = createOffering(offeringsRoute.projectId)
              return send(res, offering, 201)
            }
          }

          const patchO = matchPath('/api/v1/offerings/:id', urlPath)
          if (method === 'PATCH' && patchO) {
            await sleep(300)
            const offering = offerings.get(patchO.id)
            if (!offering) return send(res, { message: 'Not found' }, 404)
            const updates = JSON.parse(await readBody(req))
            const updated = { ...offering, ...updates }
            offerings.set(patchO.id, updated)
            return send(res, updated)
          }

          const aiP = matchPath('/api/v1/offerings/:id/ai-placement', urlPath)
          if (method === 'POST' && aiP) {
            await sleep(1800)
            const offering = offerings.get(aiP.id)
            if (!offering) return send(res, { message: 'Not found' }, 404)
            const pins = offering.selectedComponents.map((key: string) => ({
              componentKey: key as import('../types').ComponentKey,
              x: AI_PLACEMENT_DEFAULTS[key as keyof typeof AI_PLACEMENT_DEFAULTS].x,
              y: AI_PLACEMENT_DEFAULTS[key as keyof typeof AI_PLACEMENT_DEFAULTS].y,
              aiPlaced: true,
            }))
            const updated = { ...offering, componentPins: pins }
            offerings.set(aiP.id, updated)
            return send(res, pins)
          }

          const renderP = matchPath('/api/v1/offerings/:id/render', urlPath)
          if (method === 'POST' && renderP) {
            await sleep(2200)
            const offering = offerings.get(renderP.id)
            if (!offering) return send(res, { message: 'Not found' }, 404)
            const updated = { ...offering, renderComplete: true, outputImageUrl: null, outputVideoUrl: null }
            offerings.set(renderP.id, updated)
            return send(res, updated)
          }

          const completeP = matchPath('/api/v1/offerings/:id/complete', urlPath)
          if (method === 'POST' && completeP) {
            await sleep(300)
            const offering = offerings.get(completeP.id)
            if (!offering) return send(res, { message: 'Not found' }, 404)
            const updated = { ...offering, status: 'complete' as const }
            offerings.set(completeP.id, updated)
            return send(res, updated)
          }

          // ── BROCHURE ────────────────────────────────────────────────────

          const brochureRoute = matchPath('/api/v1/offerings/:offeringId/brochure', urlPath)
          if (brochureRoute) {
            if (method === 'GET') {
              await sleep(300)
              const b = [...brochures.values()].find(
                (x) => x.offeringId === brochureRoute.offeringId
              )
              if (!b) return send(res, { message: 'Not found' }, 404)
              return send(res, b)
            }

            if (method === 'POST') {
              await sleep(400)
              const body = JSON.parse(await readBody(req)) as { projectId: string }
              const existing = [...brochures.values()].find(
                (x) => x.offeringId === brochureRoute.offeringId
              )
              if (existing) return send(res, existing)
              const id = `brochure-${generateId()}`
              const brochure = {
                id,
                offeringId: brochureRoute.offeringId,
                projectId: body.projectId,
                content: {
                  offeringOverview: '',
                  competitorComparison: '',
                  uniqueSellingPoints: '',
                  customerBenefits: '',
                  additionalNotes: '',
                },
                tenderPdfUrl: null,
                sectionsComplete: 0,
                createdAt: new Date().toISOString(),
              }
              brochures.set(id, brochure)
              return send(res, brochure, 201)
            }

            if (method === 'PATCH') {
              await sleep(300)
              const b = [...brochures.values()].find(
                (x) => x.offeringId === brochureRoute.offeringId
              )
              if (!b) return send(res, { message: 'Not found' }, 404)
              const updates = JSON.parse(await readBody(req)) as {
                content?: Record<string, string>
              }
              const updatedContent = { ...b.content, ...(updates.content ?? {}) }
              const sectionsComplete = Object.values(updatedContent).filter(
                (v: string) => v.trim().length > 0
              ).length
              const updated = { ...b, content: updatedContent, sectionsComplete }
              brochures.set(b.id, updated)
              return send(res, updated)
            }
          }

          // ── VIDEO PIPELINE ───────────────────────────────────────────────

          if (method === 'POST' && urlPath === '/api/v1/video/upload-image') {
            await sleep(500)
            return send(res, {
              success: true,
              message: 'Image uploaded',
              imageId: `mock-img-${generateId()}`,
            })
          }

          if (method === 'POST' && urlPath === '/api/v1/video/select-environment') {
            await sleep(200)
            const body = JSON.parse(await readBody(req)) as { environment: string }
            return send(res, { success: true, selectedEnvironment: body.environment })
          }

          if (method === 'POST' && urlPath === '/api/v1/video/select-components') {
            await sleep(200)
            const body = JSON.parse(await readBody(req)) as { components: unknown }
            return send(res, { success: true, selectedComponents: body.components })
          }

          if (method === 'POST' && urlPath === '/api/v1/video/generate') {
            await sleep(1200)
            return send(res, {
              success: true,
              message: 'Video generated successfully',
              data: { imageId: 'mock', outputImage: '/mock/output.jpg', outputVideo: '/mock/output.mp4' },
            })
          }

          // Unmatched /api/ route
          send(res, { message: 'Not found' }, 404)
        } catch (err) {
          console.error('[Mock API]', err)
          send(res, { message: 'Internal server error' }, 500)
        }
      })
    },
  }
}
