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
  bbox?: [number, number, number, number]
  imageWidth?: number
  imageHeight?: number
  editableLayerUrl?: string | null
  repinBackgroundUrl?: string | null
  repinBackgroundDisplayUrl?: string | null
}

export type RepinFeedbackOption =
  | 'edge_alignment'
  | 'perspective_depth'
  | 'lighting_shadow'
  | 'material_reflections'
  | 'seamless_blending'

export interface RepinTransform {
  componentKey: ComponentKey
  componentType: ComponentKey
  sourceVersion: number
  targetVersion: number
  x: number
  y: number
  width: number
  height: number
  rotation: number
  skewX: number
  skewY: number
  coordinateSpace?: 'pixels' | 'percent'
  imageWidth?: number
  imageHeight?: number
  editableLayerUrl?: string | null
  repinBackgroundUrl?: string | null
  repinBackgroundDisplayUrl?: string | null
  editableLayerPath?: string | null
  repinBackgroundPath?: string | null
  feedbackOption?: RepinFeedbackOption | null
  feedbackOptions?: RepinFeedbackOption[]
  sourceBaseMode?: 'original' | 'version'
  sourceVersionComponent?: ComponentKey | null
}

export interface PreviewVersion {
  version: number
  url: string
  createdAt?: string
  sourceVersion?: number
  transform?: RepinTransform
  feedbackOption?: RepinFeedbackOption | null
  feedbackOptions?: RepinFeedbackOption[]
  sourceBaseMode?: 'original' | 'version'
  sourceVersionComponent?: ComponentKey | null
}

export type OfferingStatus = 'draft' | 'active' | 'complete'

export interface Offering {
  id: string
  projectId: string
  name: string
  status: OfferingStatus
  createdAt: string
  imageId: string | null
  inputImagePath?: string | null
  previewImagePath?: string | null
  outputImagePath?: string | null
  outputVideoPath?: string | null
  uploadedFileUrl: string | null
  uploadedFileName: string | null
  uploadedFileType: 'image' | 'video' | null
  environments: Environment[]
  selectedComponents: ComponentKey[]
  componentPins: ComponentPin[]
  annotationsEnabled: boolean
  activeAnnotationFilters: ComponentKey[]
  videoMotionStyle: 'zoom-in' | 'pan-lr' | 'pan-rl' | 'door-functionality'
  videoSpeed: 0.5 | 1 | 1.5
  videoQuality: '360p' | '480p' | '720p' | '1080p'
  renderComplete: boolean
  pipelineStatus?: 'idle' | 'uploaded' | 'processing' | 'preview_ready' | 'video_ready' | 'ready_for_download' | 'failed'
  outputImageUrl: string | null
  outputVideoUrl: string | null
  lastError?: string | null
  savedStep?: OfferingStep
  previewRequestKey?: string | null
  previewVersions?: PreviewVersion[]
  repinPass?: number
  repinTransforms?: Partial<Record<ComponentKey, RepinTransform>>
  videoGenerated?: boolean
  downloadUrl?: string | null
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
