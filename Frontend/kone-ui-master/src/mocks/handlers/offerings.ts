import { http, HttpResponse, delay } from 'msw'
import { offerings, createOffering } from '../data/seed'
import { generateId } from '../../lib/utils'
import { AI_PLACEMENT_DEFAULTS } from '../../lib/constants'
import type { ComponentKey, ComponentPin } from '../../types'

export const offeringHandlers = [
  http.get('/api/v1/projects/:projectId/offerings', async ({ params }) => {
    await delay(350)
    const projectOfferings = [...offerings.values()].filter(
      o => o.projectId === params.projectId
    )
    return HttpResponse.json(projectOfferings)
  }),

  http.post('/api/v1/projects/:projectId/offerings', async ({ params }) => {
    await delay(400)
    const offering = createOffering(params.projectId as string)
    return HttpResponse.json(offering, { status: 201 })
  }),

  http.patch('/api/v1/offerings/:id', async ({ params, request }) => {
    await delay(300)
    const offering = offerings.get(params.id as string)
    if (!offering) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    const updates = (await request.json()) as Partial<typeof offering>
    const updated = { ...offering, ...updates }
    offerings.set(params.id as string, updated)
    return HttpResponse.json(updated)
  }),

  http.post('/api/v1/offerings/:id/ai-placement', async ({ params }) => {
    await delay(1800)
    const offering = offerings.get(params.id as string)
    if (!offering) return HttpResponse.json({ message: 'Not found' }, { status: 404 })

    const pins: ComponentPin[] = offering.selectedComponents.map((key: ComponentKey) => ({
      componentKey: key,
      x: AI_PLACEMENT_DEFAULTS[key].x,
      y: AI_PLACEMENT_DEFAULTS[key].y,
      aiPlaced: true,
    }))

    const updated = { ...offering, componentPins: pins }
    offerings.set(params.id as string, updated)
    return HttpResponse.json(pins)
  }),

  http.post('/api/v1/offerings/:id/render', async ({ params }) => {
    await delay(2200)
    const offering = offerings.get(params.id as string)
    if (!offering) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    const updated = { ...offering, renderComplete: true, outputImageUrl: null, outputVideoUrl: null }
    offerings.set(params.id as string, updated)
    return HttpResponse.json(updated)
  }),

  http.post('/api/v1/offerings/:id/complete', async ({ params }) => {
    await delay(300)
    const offering = offerings.get(params.id as string)
    if (!offering) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    const updated = { ...offering, status: 'complete' as const }
    offerings.set(params.id as string, updated)
    return HttpResponse.json(updated)
  }),

  // Video pipeline mocks (used when mocks are enabled)
  http.post('/api/v1/video/upload-image', async () => {
    await delay(500)
    return HttpResponse.json({
      success: true,
      message: 'Image uploaded',
      imageId: `mock-img-${generateId()}`,
    })
  }),

  http.post('/api/v1/video/select-environment', async ({ request }) => {
    await delay(200)
    const body = (await request.json()) as { environment: string }
    return HttpResponse.json({ success: true, selectedEnvironment: body.environment })
  }),

  http.post('/api/v1/video/select-components', async ({ request }) => {
    await delay(200)
    const body = (await request.json()) as { components: unknown }
    return HttpResponse.json({ success: true, selectedComponents: body.components })
  }),

  http.post('/api/v1/video/generate', async () => {
    await delay(1200)
    return HttpResponse.json({
      success: true,
      message: 'Video generated successfully',
      data: { imageId: 'mock', outputImage: '/mock/output.jpg', outputVideo: '/mock/output.mp4' },
    })
  }),
]
