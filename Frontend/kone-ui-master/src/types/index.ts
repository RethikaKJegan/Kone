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
export type SemanticComponentKey = 'ceiling' | 'kds' | 'dcs1020' | 'lci' | 'door' | 'cop'
export type ComponentKey = SemanticComponentKey | 'kds_2' | 'kds_3'

export interface ComponentItem {
  key: ComponentKey
  label: string
  description: string
  imageUrl?: string
  variants?: ComponentVariant[]
}

export interface ComponentVariant {
  id: string
  label: string
  imageUrl: string
  group?: string
}

export interface ComponentInstanceSelection {
  id: string
  componentType: SemanticComponentKey
  variantId: string
  assetUrl: string
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

export interface EraserHistoryEntry {
  repinBackgroundUrl: string | null
  repinBackgroundDisplayUrl: string | null
}

export interface RepinSharedBackgroundState {
  repinBackgroundUrl: string | null
  repinBackgroundDisplayUrl: string | null
  eraserHistory: EraserHistoryEntry[]
  eraserRedoStack: EraserHistoryEntry[]
}

export interface RepinTransform {
  componentId?: string | null
  componentKey: ComponentKey
  componentType: SemanticComponentKey
  sourceVersion: number
  targetVersion: number
  x: number
  y: number
  width: number
  height: number
  rotation: number
  skewX: number
  skewY: number
  points?: [
    { x: number; y: number },
    { x: number; y: number },
    { x: number; y: number },
    { x: number; y: number },
  ]
  coordinateSpace?: 'pixels' | 'percent'
  imageWidth?: number
  imageHeight?: number
  assetAspectRatio?: number | null
  originalBbox?: [number, number, number, number] | null
  originalImageWidth?: number | null
  originalImageHeight?: number | null
  editableLayerUrl?: string | null
  repinBackgroundUrl?: string | null
  repinBackgroundDisplayUrl?: string | null
  eraserHistory?: EraserHistoryEntry[]
  eraserRedoStack?: EraserHistoryEntry[]
  editableLayerPath?: string | null
  repinBackgroundPath?: string | null
  feedbackOption?: RepinFeedbackOption | null
  feedbackOptions?: RepinFeedbackOption[]
  sourceBaseMode?: 'original' | 'version'
  sourceVersionComponent?: ComponentKey | null
  sourceVersionComponentId?: string | null
  parentVersionId?: number | null
  parentFinalImagePath?: string | null
  activeComponentId?: string | null
  activeComponentType?: SemanticComponentKey | null
  currentComponentMaskOrCrop?: [number, number, number, number] | null
  magicEraserApplied?: boolean
}

export interface PreviewVersion {
  version: number
  url: string
  createdAt?: string
  sourceVersion?: number
  parentVersionId?: number | null
  parentFinalImagePath?: string | null
  finalImagePath?: string | null
  transform?: RepinTransform
  transforms?: RepinTransform[]
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
  selectedComponentAssets?: Partial<Record<ComponentKey, string>>
  componentInstances?: ComponentInstanceSelection[]
  componentPins: ComponentPin[]
  annotationsEnabled: boolean
  activeAnnotationFilters: ComponentKey[]
  videoMotionStyle: 'zoom-in' | 'pan' | 'door-functionality'
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
  selectedOutputVersion?: number
  repinTransforms?: Partial<Record<string, RepinTransform>>
  repinSharedBackgrounds?: Record<string, RepinSharedBackgroundState>
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
