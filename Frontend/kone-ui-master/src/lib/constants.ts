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
      { id: 'art-deco', label: 'Art Deco', imageUrl: '/components/elevator-interior/Art Deco.png' },
    ],
  },
  {
    key: 'lci',
    label: 'LCI',
    description: 'Landing Call Indicator',
    imageUrl: '/components/lci/KDS90/Landing Call Indicator Flush - Up.png',
    variants: [
      { id: 'kds90-lci-flush-up', group: 'KDS90', label: 'Landing Call Indicator Flush - Up', imageUrl: '/components/lci/KDS90/Landing Call Indicator Flush - Up.png' },
      { id: 'kds90-lci-surface-up', group: 'KDS90', label: 'Landing Call Indicator Surface - Up', imageUrl: '/components/lci/KDS90/Landing Call Indicator Surface - Up.png' },
      { id: 'kds90-car-interface-7-segment', group: 'KDS90', label: 'Car Interface - 7 Segment', imageUrl: '/components/lci/KDS90/Car Interface - 7 Segment.png' },
      { id: 'kds90-lci-flush-up-down', group: 'KDS90', label: 'Landing Call Indicator Flush - Up/Down', imageUrl: '/components/lci/KDS90/Landing Call Indicator Flush - Up Down.png' },
      { id: 'kds90-lci-surface-up-down', group: 'KDS90', label: 'Landing Call Indicator Surface - Up/Down', imageUrl: '/components/lci/KDS90/Landing Call Indicator Surface - UpDown.png' },
      { id: 'kds90-car-interface-dot-matrix', group: 'KDS90', label: 'Car Interface - Dot Matrix', imageUrl: '/components/lci/KDS90/Car Interface - Dot Matrix.png' },
      { id: 'kds330-lci-flush', group: 'KDS330', label: 'Landing Call Indicator Flush', imageUrl: '/components/lci/KDS330/Landing Call Indicator Flush.png' },
      { id: 'kds330-lci-surface', group: 'KDS330', label: 'Landing Call Indicator Surface', imageUrl: '/components/lci/KDS330/Landing Call Indicator Surface.png' },
      { id: 'kds330-hall-lantern-flush-up-down', group: 'KDS330', label: 'Hall Lantern Flush - Up/Down', imageUrl: '/components/lci/KDS330/Hall Lantern Flush - Up Down.png' },
      { id: 'kds330-hall-lantern-surface', group: 'KDS330', label: 'Hall Lantern Surface', imageUrl: '/components/lci/KDS330/Hall Lantern Surface.png' },
      { id: 'kds330-hall-indicator-flush-7-segment', group: 'KDS330', label: 'Hall Indicator Flush - 7 Segment', imageUrl: '/components/lci/KDS330/Hall Indicator Flush - 7 Segment.png' },
      { id: 'kds330-hall-indicator-surface', group: 'KDS330', label: 'Hall Indicator Surface', imageUrl: '/components/lci/KDS330/Hall Indicator Surface.png' },
      { id: 'kds330-landing-call-station-flush', group: 'KDS330', label: 'Landing Call Station Flush', imageUrl: '/components/lci/KDS330/Landing Call Station Flush.png' },
      { id: 'kds330-landing-call-station-surface', group: 'KDS330', label: 'Landing Call Station Surface', imageUrl: '/components/lci/KDS330/Landing Call Station Surface.png' },
      { id: 'dcs1020-pedestal-mounted-dop-ksp1068', group: 'DCS1020', label: 'Pedestal Mounted DOP KSP1068', imageUrl: '/components/lci/DCS1020/Pedestal Mounted DOP KSP1068.png' },
      { id: 'dcs1020-wall-mounted-10in-dop-ksp1068', group: 'DCS1020', label: 'Wall Mounted 10" DOP KSP1068', imageUrl: '/components/lci/DCS1020/Wall Mounted 10in DOP KSP1068.png' },
      { id: 'dcs1020-destination-guidance-dual-kst1078', group: 'DCS1020', label: 'Destination Guidance Dual KST1078', imageUrl: '/components/lci/DCS1020/Destination Guidance Dual KST1078.png' },
      { id: 'dcs1020-elevator-guide', group: 'DCS1020', label: 'Elevator Guide', imageUrl: '/components/lci/DCS1020/Elevator Guide.png' },
      { id: 'dcs1020-destination-guidance-single-kst1068', group: 'DCS1020', label: 'Destination Guidance Single KST1068', imageUrl: '/components/lci/DCS1020/Destination Guidance Dual KST1068.png' },
      { id: 'dcs1020-kst-850-860', group: 'DCS1020', label: 'KST 850/860', imageUrl: '/components/lci/DCS1020/KST 850-860.png' },
      { id: 'dcs1020-kso-857', group: 'DCS1020', label: 'KSO 857', imageUrl: '/components/lci/DCS1020/KSO 857.png' },
      { id: 'dcs1020-eid-kst-880-890', group: 'DCS1020', label: 'EID KST 880-890', imageUrl: '/components/lci/DCS1020/EID KST 880-890.png' },
      { id: 'dcs1020-wall-mounted-7in-dop-ksp1028', group: 'DCS1020', label: 'Wall Mounted 7" DOP KSP1028', imageUrl: '/components/lci/DCS1020/Wall Mounted 7” DOP KSP1028.png' },
    ],
  },
  {
    key: 'door',
    label: 'Door',
    description: 'KONE door system',
    imageUrl: '/components/door/Plain Stainless Steel Door.png',
    variants: [
      { id: 'plain-stainless-steel-door', label: 'Plain Stainless Steel Door', imageUrl: '/components/door/Plain Stainless Steel Door.png' },
      { id: 'stainless-steel-door', label: 'Stainless Steel Door', imageUrl: '/components/door/Solid Stainless Steel Door.png' },
      { id: 'small-vision-glass-door', label: 'Small Vision Glass Door', imageUrl: '/components/door/Small vision glass door .png' },
      { id: 'half-glass-door', label: 'Half Glass Door', imageUrl: '/components/door/Half glass door.png' },
      { id: 'framed-full-glass-door', label: 'Framed Full Glass Door', imageUrl: '/components/door/Framed full glass door.png' },
      { id: 'frameless-full-glass-door', label: 'Frameless Full Glass Door', imageUrl: '/components/door/Frameless full glass door.png' },
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
