import { http, HttpResponse, delay } from 'msw'
import { projects, getUserFromToken, createProject } from '../data/seed'

export const projectHandlers = [
  http.get('/api/v1/projects', async ({ request }) => {
    await delay(400)
    const auth = request.headers.get('Authorization')
    const user = getUserFromToken(auth)
    if (!user) return HttpResponse.json([], { status: 200 })

    const userProjects = [...projects.values()].filter(p => p.userId === user.id)
    return HttpResponse.json(userProjects)
  }),

  http.post('/api/v1/projects', async ({ request }) => {
    await delay(500)
    const auth = request.headers.get('Authorization')
    const user = getUserFromToken(auth)
    const body = (await request.json()) as { name: string }

    if (!body.name || body.name.length < 2 || body.name.length > 80) {
      return HttpResponse.json({ code: 400, message: 'Project name must be 2–80 characters' }, { status: 400 })
    }

    const userId = user?.id ?? `guest-${Date.now()}`
    const project = createProject(body.name, userId)
    return HttpResponse.json(project, { status: 201 })
  }),

  http.delete('/api/v1/projects/:id', async ({ params }) => {
    await delay(300)
    projects.delete(params.id as string)
    return new HttpResponse(null, { status: 204 })
  }),
]
