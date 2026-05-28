import { setupWorker } from 'msw/browser'
import { authHandlers } from './handlers/auth'
import { projectHandlers } from './handlers/projects'
import { offeringHandlers } from './handlers/offerings'
import { brochureHandlers } from './handlers/brochure'

export const worker = setupWorker(
  ...authHandlers,
  ...projectHandlers,
  ...offeringHandlers,
  ...brochureHandlers
)
