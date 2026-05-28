export type UserRole = 'authenticated' | 'guest'

export interface User {
  id: string
  email: string
  name: string
  role: UserRole
  company: string
  avatarInitials: string
}

export type ProjectStatus = 'draft' | 'active' | 'complete'

export interface Project {
  id: string
  name: string
  status: ProjectStatus
  createdAt: string
  updatedAt: string
  offeringCount: number
  userId: string
}

export type Environment = 'car' | 'lobby'
export type ComponentKey = 'ceiling' | 'lci' | 'door' | 'cop'

export interface ComponentItem {
  key: ComponentKey
  label: string
  description: string
  imageUrl?: string
}

export interface ComponentPin {
  componentKey: ComponentKey
  x: number
  y: number
  aiPlaced: boolean
}

export type OfferingStatus = 'draft' | 'complete'

export interface Offering {
  id: string
  projectId: string
  name: string
  status: OfferingStatus
  createdAt: string
  imageId: string | null
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
  outputImageUrl: string | null
  outputVideoUrl: string | null
}

export type BrochureSection =
  | 'offeringOverview'
  | 'competitorComparison'
  | 'uniqueSellingPoints'
  | 'customerBenefits'
  | 'additionalNotes'

export interface BrochureContent {
  offeringOverview: string
  competitorComparison: string
  uniqueSellingPoints: string
  customerBenefits: string
  additionalNotes: string
}

export interface Brochure {
  id: string
  offeringId: string
  projectId: string
  content: BrochureContent
  tenderPdfUrl: string | null
  sectionsComplete: number
  createdAt: string
}

export type OfferingStep = 1 | 2 | 3 | 4 | 5 | 6

export interface StepMeta {
  step: OfferingStep
  label: string
  completed: boolean
}
