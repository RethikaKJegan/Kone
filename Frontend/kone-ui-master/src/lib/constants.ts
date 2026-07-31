import type { ComponentItem, Environment, OfferingStep, BrochureSection, User } from '../types'

export const KONE_COMPONENTS: ComponentItem[] = [
  {
    key: 'ceiling',
    label: 'Elevator Interior',
    description: 'KONE elevator interior unit',
    imageUrl: '/components/elevator-interior/A MonoSpace.png',
    variants: [
      { id: 'a-monospace', label: 'A MonoSpace', imageUrl: '/components/elevator-interior/A MonoSpace.png' },
      { id: 'i-monospace', label: 'I MonoSpace', imageUrl: '/components/elevator-interior/I MonoSpace.png' },
      { id: 'ii-monospace', label: 'II MonoSpace', imageUrl: '/components/elevator-interior/II MonoSpace.png' },
      { id: 'monospace-dx', label: 'MonoSpace DX', imageUrl: '/components/elevator-interior/MonoSpace DX.png' },
      { id: 'monospace-dx1', label: 'MonoSpace DX1', imageUrl: '/components/elevator-interior/MonoSpace DX1.png' },
      { id: 'monospace-dx2', label: 'MonoSpace DX2', imageUrl: '/components/elevator-interior/MonoSpace DX2.png' },
    ],
  },
  {
    key: 'lci',
    label: 'LCI',
    description: 'Landing Call Indicator',
    imageUrl: '/components/lci/lci-flush-up.png',
    variants: [
      { id: 'lci-flush-up', label: 'LCI Flush - Up', imageUrl: '/components/lci/lci-flush-up.png' },
      { id: 'lci-surface-up', label: 'LCI Surface - Up', imageUrl: '/components/lci/lci-surface-up.png' },
      { id: 'ci-7-segment', label: 'CI - 7 Segment', imageUrl: '/components/lci/ci-7-segment.png' },
      { id: 'lci-flush-up-down', label: 'LCI Flush - Up/Down', imageUrl: '/components/lci/lci-flush-up-down.png' },
      { id: 'lci-surface-up-down', label: 'LCI Surface - Up/Down', imageUrl: '/components/lci/LCI Surface – UpDown.png' },
      { id: 'ci-dot-matrix', label: 'CI - Dot Matrix', imageUrl: '/components/lci/ci-dot-matrix.png' },
      { id: 'hi-flush-7-segment', label: 'HI Flush 7 Segment', imageUrl: '/components/lci/HI Flush_7 Segment.png' },
      { id: 'lci-flush', label: 'LCI Flush', imageUrl: '/components/lci/LCI Flush.png' },
      { id: 'hl-flush-up-down', label: 'HL Flush Up/Down', imageUrl: '/components/lci/HL Flush_Up_Down.png' },
      { id: 'destination-surface', label: 'Destination Surface', imageUrl: '/components/lci/Destination Surface.png' },
      { id: 'destination-surface-1', label: 'Destination Surface 1', imageUrl: '/components/lci/Destination Surface_1.png' },
      { id: 'lcs-flush', label: 'LCS Flush', imageUrl: '/components/lci/LCS Flush.png' },
      { id: 'elevator-guide', label: 'Elevator Guide', imageUrl: '/components/lci/Elevator Guide.png' },
      { id: 'kso-857', label: 'KSO 857', imageUrl: '/components/lci/KSO 857.png' },
      { id: 'advance-guidance-single', label: 'Advance Guidance - Single', imageUrl: '/components/lci/Advance Guidance - Single.png' },
      { id: 'advance-guidance-dual', label: 'Advance Guidance - Dual', imageUrl: '/components/lci/Advance Guidance.png' },
      { id: 'kst-880-890', label: 'KST 880/890', imageUrl: '/components/lci/KST 880_890.png' },
      { id: 'kst-850-860', label: 'KST 850/860', imageUrl: '/components/lci/KST 850_860.png' },
    ],
  },
  {
    key: 'door',
    label: 'Door',
    description: 'KONE door system',
    imageUrl: '/components/door/Door1.png',
    variants: [
      { id: 'door-1', label: 'Door 1', imageUrl: '/components/door/Door1.png' },
    ],
  },
  {
    key: 'cop',
    label: 'COP',
    description: 'Car Operating Panel',
    imageUrl: '/components/cop/Flush COP.png',
    variants: [
      { id: 'flush-cop', label: 'Flush COP', imageUrl: '/components/cop/Flush COP.png' },
      { id: 'swing-cop', label: 'Swing COP', imageUrl: '/components/cop/Swing COP.png' },
      { id: 'swing-keypad-cop', label: 'Swing Keypad COP', imageUrl: '/components/cop/Swing Keypad COP.png' },
      { id: 'swing-emergency-communications-cop', label: 'Swing Emergency Communications COP', imageUrl: '/components/cop/Swing Emergency Communications COP.png' },
    ],
  },
]

export const ENVIRONMENTS: { key: Environment; label: string }[] = [
  { key: 'car', label: 'Car' },
  { key: 'lobby', label: 'Lobby' },
]

export const STEP_LABELS: Record<OfferingStep, string> = {
  1: 'Upload',
  2: 'Components',
  3: 'Preview',
  4: 'Repin',
  5: 'Video',
  6: 'Download',
}

export const OPTIONAL_STEPS: OfferingStep[] = [4]

export const VIDEO_MOTION_STYLES = [
  { value: 'zoom-in', label: 'Zoom In' },
  { value: 'pan', label: 'Pan' },
  { value: 'door-functionality', label: 'Door Functionality' },
] as const

export const VIDEO_SPEEDS = [0.5, 1, 1.5] as const
export const VIDEO_QUALITIES = ['360p', '480p', '720p', '1080p'] as const

export const BROCHURE_SECTIONS: {
  key: BrochureSection
  label: string
  placeholder: string
}[] = [
  {
    key: 'offeringOverview',
    label: 'Visualization Overview',
    placeholder:
      'Describe the elevator solution being proposed — components included, configuration details, and why it suits the customer environment.',
  },
  {
    key: 'competitorComparison',
    label: 'Competitor Comparison',
    placeholder:
      'Summarise how this KONE solution compares to competitor visualizations in terms of quality, service, and lifecycle cost.',
  },
  {
    key: 'uniqueSellingPoints',
    label: 'Unique Selling Points (U.S.P.)',
    placeholder:
      'List what differentiates this KONE solution — technology, reliability, design flexibility, or global service network.',
  },
  {
    key: 'customerBenefits',
    label: 'Customer Benefits (X.Y.Z.)',
    placeholder:
      'Frame benefits as outcomes for the customer: reliability, downtime reduction, warranty coverage, modernisation value.',
  },
  {
    key: 'additionalNotes',
    label: 'Additional Notes (A.B.C.)',
    placeholder:
      'Include any additional commercial terms, project timelines, or post-installation support details.',
  },
]

export const GUEST_USER: User = {
  id: 'guest',
  email: 'guest@kone.com',
  name: 'Guest User',
  role: 'guest',
  company: 'KONE',
  avatarInitials: 'GU',
}

export const AI_PLACEMENT_DEFAULTS = {
  ceiling: { x: 50, y: 10 },
  lci: { x: 78, y: 40 },
  door: { x: 20, y: 55 },
  cop: { x: 18, y: 52 },
} as const
