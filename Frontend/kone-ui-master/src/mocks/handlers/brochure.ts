import { http, HttpResponse, delay } from 'msw'
import { brochures } from '../data/seed'
import { generateId } from '../../lib/utils'
import type { Brochure, BrochureContent } from '../../types'

function countSections(content: BrochureContent): number {
  return Object.values(content).filter(v => v.trim().length > 0).length
}

export const brochureHandlers = [
  http.get('/api/v1/offerings/:offeringId/brochure', async ({ params }) => {
    await delay(300)
    const brochure = [...brochures.values()].find(b => b.offeringId === params.offeringId)
    if (!brochure) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    return HttpResponse.json(brochure)
  }),

  http.post('/api/v1/offerings/:offeringId/brochure', async ({ params, request }) => {
    await delay(400)
    const body = (await request.json()) as { projectId: string }
    const existing = [...brochures.values()].find(b => b.offeringId === params.offeringId)
    if (existing) return HttpResponse.json(existing)
    const id = `brochure-${generateId()}`
    const brochure: Brochure = {
      id,
      offeringId: params.offeringId as string,
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
    return HttpResponse.json(brochure, { status: 201 })
  }),

  http.patch('/api/v1/offerings/:offeringId/brochure', async ({ params, request }) => {
    await delay(300)
    const brochure = [...brochures.values()].find(b => b.offeringId === params.offeringId)
    if (!brochure) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    const updates = (await request.json()) as { content?: Partial<BrochureContent> }
    const updatedContent = { ...brochure.content, ...(updates.content ?? {}) }
    const updated: Brochure = {
      ...brochure,
      content: updatedContent,
      sectionsComplete: countSections(updatedContent),
    }
    brochures.set(brochure.id, updated)
    return HttpResponse.json(updated)
  }),
]
