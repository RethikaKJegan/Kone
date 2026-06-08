import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Loader2, Image as ImageIcon, Layers, Video, Download, Eye, EyeOff, FileText, ArrowLeft, CheckCircle2 } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { useAuthStore } from '../../../store/authStore'
import { AnnotatedPreview } from '../../../components/shared/AnnotatedPreview'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { cn } from '../../../lib/utils'
import type { ComponentKey, ComponentPin } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>
type DownloadType = 'image' | 'annotations' | 'video'
type ComponentBrochureId = 'cop' | 'lci' | 'interior' | 'door'

const componentKeyToBrochureId: Record<ComponentKey, ComponentBrochureId> = {
  cop: 'cop',
  lci: 'lci',
  ceiling: 'interior',
  door: 'door',
}

function downloadFromUrl(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

const componentBrochureData = {
  cop: {
    id: 'cop',
    name: 'COP',
    fullName: 'Car Operating Panel',
    page2Title: 'Car Operating Panel Modernization',
    page2Description: 'A modern COP improves daily passenger interaction with clearer controls, better visibility, durable buttons, and accessible operation inside the cabin.',
    purpose: 'Provides passengers with floor selection, door control, emergency alarm access, status feedback, and communication interface inside the elevator cabin.',
    keyUpgrades: 'Digital display, tactile buttons, alarm, door controls, LED feedback, and a modern faceplate finish.',
    materialsFinish: 'Brushed stainless steel or powder-coated metal faceplate with black display window and flush-mounted control modules.',
    safetyCompliance: 'Emergency alarm operation, clear visual feedback, accessible button placement, tactile markings, and braille-ready legends.',
    maintenanceBenefit: 'Modular button, display, and communication modules reduce troubleshooting time and recurring faults from aged controls.',
    technicalSpecs: [
      ['Installation Area', 'Inside elevator cabin'],
      ['Primary Function', 'Passenger floor selection and cabin control'],
      ['Display Type', 'Digital floor / direction indicator'],
      ['Button Type', 'Tactile illuminated push buttons'],
      ['Emergency Feature', 'Alarm and intercom speaker provision'],
      ['Finish Options', 'Stainless steel / powder-coated metal'],
      ['Accessibility', 'Braille-ready and tactile marking support'],
    ],
  },
  lci: {
    id: 'lci',
    name: 'LCI',
    fullName: 'Landing Call Indicator',
    page2Title: 'Landing Call Indicator Modernization',
    page2Description: 'A modern LCI improves landing visibility and helps passengers clearly identify elevator direction, arrival status, and call registration.',
    purpose: 'Allows passengers to call the elevator from the landing and receive visual feedback for direction, floor position, and registered calls.',
    keyUpgrades: 'Digital floor display, direction arrow, up/down call buttons, illuminated call feedback, service icons, and compact wall-mounted fixture design.',
    materialsFinish: 'Metal faceplate with black glass or acrylic display window, integrated LED indicators, and tactile call buttons.',
    safetyCompliance: 'Clear call confirmation, direction indication, and visible service / alert status symbols improve passenger guidance.',
    maintenanceBenefit: 'Replaceable indicator and button modules allow faster servicing without replacing the complete landing fixture.',
    technicalSpecs: [
      ['Installation Area', 'Elevator landing / floor lobby'],
      ['Primary Function', 'Landing call registration and direction display'],
      ['Display Type', 'Digital floor indicator with arrow direction'],
      ['Button Type', 'Up / down tactile call buttons'],
      ['Status Indication', 'Call feedback and alert icons'],
      ['Finish Options', 'Stainless steel / aluminum / powder-coated metal'],
      ['Mounting', 'Wall-mounted landing fixture'],
    ],
  },
  interior: {
    id: 'interior',
    name: 'Elevator Interior',
    fullName: 'Elevator Cabin Interior',
    page2Title: 'Elevator Interior Modernization',
    page2Description: 'Cabin interior modernization refreshes the passenger experience with better lighting, cleaner wall finishes, durable handrails, and improved visual appeal.',
    purpose: 'Improves cabin appearance, comfort, lighting quality, durability, passenger confidence, and the perceived value of the building.',
    keyUpgrades: 'Decorative wall panels, feature rear wall, side wall cladding, recessed LED lights, handrail, durable flooring, and cleaner cabin detailing.',
    materialsFinish: 'Decorative laminate, stainless steel, patterned metal, PVC-coated panels, powder-coated panels, anti-skid flooring, and stainless or coated handrails.',
    safetyCompliance: 'Improved illumination, secure handrail placement, non-slip flooring options, and fire-rated material selection where required.',
    maintenanceBenefit: 'Replaceable wall panels, washable finishes, and durable flooring reduce visible wear and simplify long-term cabin upkeep.',
    technicalSpecs: [
      ['Installation Area', 'Inside elevator cabin'],
      ['Primary Function', 'Cabin appearance, comfort, and durability upgrade'],
      ['Wall Finish', 'Laminate / metal / decorative panel system'],
      ['Ceiling', 'Recessed LED lighting ceiling'],
      ['Handrail', 'Stainless steel or powder-coated rail'],
      ['Flooring', 'Anti-skid vinyl / tile / durable cabin flooring'],
      ['Serviceability', 'Replaceable wall, ceiling, and lighting modules'],
    ],
  },
  door: {
    id: 'door',
    name: 'Elevator Door',
    fullName: 'Elevator Door Modernization',
    page2Title: 'Elevator Door Modernization',
    page2Description: 'Door modernization improves the entrance experience with cleaner finishes, smoother operation, better alignment, and a more durable landing or cabin door surface.',
    purpose: 'Provides safe passenger entry and exit, protects the lift opening, supports reliable door operation, and improves the elevator entrance appearance.',
    keyUpgrades: 'Stainless steel door panels, center-opening alignment, refreshed entrance finish, reopening protection compatibility, sill / jamb detailing, and smoother movement.',
    materialsFinish: 'Brushed stainless steel, hairline stainless steel, powder-coated steel, or patterned metal panels with matching jamb, header, and sill options.',
    safetyCompliance: 'Proper door closing, clear opening alignment, reopening device compatibility, landing entrance protection, and applicable door safety requirements.',
    maintenanceBenefit: 'Renewed panels, tracks, rollers, and entrance finishes reduce visible wear, noise, vibration, and frequent adjustment needs.',
    technicalSpecs: [
      ['Installation Area', 'Cabin entrance and / or landing entrance'],
      ['Primary Function', 'Passenger access and lift entrance protection'],
      ['Door Type', 'Automatic center-opening elevator door'],
      ['Panel Finish', 'Brushed / hairline stainless steel'],
      ['Entrance Finish', 'Matching jamb, header, and sill options'],
      ['Safety Interface', 'Reopening device compatibility'],
      ['Serviceability', 'Accessible tracks, rollers, hangers, and sill parts'],
    ],
  },
} satisfies Record<ComponentBrochureId, {
  id: ComponentBrochureId
  name: string
  fullName: string
  page2Title: string
  page2Description: string
  purpose: string
  keyUpgrades: string
  materialsFinish: string
  safetyCompliance: string
  maintenanceBenefit: string
  technicalSpecs: [string, string][]
}>

function withTimeout<T>(promise: Promise<T>, ms: number, message: string) {
  return new Promise<T>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error(message)), ms)
    promise
      .then(value => {
        window.clearTimeout(timeout)
        resolve(value)
      })
      .catch(error => {
        window.clearTimeout(timeout)
        reject(error)
      })
  })
}

async function imageUrlToDataUrl(url: string | null | undefined) {
  if (!url || url.startsWith('data:')) return url ?? ''
  try {
    const response = await fetch(url, { credentials: 'include' })
    if (!response.ok) return url
    const blob = await response.blob()
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('Could not read brochure image'))
      reader.readAsDataURL(blob)
    })
  } catch {
    return url
  }
}

function componentAsset(id: ComponentBrochureId) {
  if (id === 'interior') return '/components/ceiling.jpg'
  if (id === 'door') return '/components/door.jpg'
  return `/components/${id}.png`
}

function getSelectedBrochureIds(offering: NonNullable<ReturnType<typeof useOfferingStore.getState>['currentOffering']>) {
  const selectedComponentKeys: ComponentKey[] = offering.selectedComponents.length ? offering.selectedComponents : ['cop']
  return [...new Set(selectedComponentKeys.map(key => componentKeyToBrochureId[key]))]
}

async function generateBrochurePdf(offering: NonNullable<ReturnType<typeof useOfferingStore.getState>['currentOffering']>) {
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
  const selectedIds = getSelectedBrochureIds(offering)
  const primary = componentBrochureData[selectedIds[selectedIds.length - 1] ?? 'cop']
  const beforeImage = await imageUrlToDataUrl(offering.uploadedFileUrl ?? offering.outputImageUrl)
  const afterImage = await imageUrlToDataUrl(offering.outputImageUrl ?? offering.uploadedFileUrl)
  const componentImages = Object.fromEntries(
    await Promise.all(Object.values(componentBrochureData).map(async component => [component.id, await imageUrlToDataUrl(componentAsset(component.id))]))
  ) as Record<ComponentBrochureId, string>

  const pageW = 210
  const pageH = 297
  const m = 13.75
  const blue = '#1A6AFF'
  const cyan = '#00B4E6'
  const dark = '#0A1628'
  const navy = '#0D2045'
  const pale = '#EEF3FF'
  const pale2 = '#F6F9FF'
  const border = '#D6E2F8'
  const ink = '#1A2B45'
  const muted = '#5A6E8C'
  const lightBlue = '#8AABF0'

  const text = (value: string, x: number, y: number, size = 10, color = ink, style: 'normal' | 'bold' = 'normal', maxWidth = 178) => {
    pdf.setFont('helvetica', style)
    pdf.setFontSize(size)
    pdf.setTextColor(color)
    pdf.text(pdf.splitTextToSize(value, maxWidth), x, y)
  }
  const serif = (value: string, x: number, y: number, size: number, color = ink, style: 'normal' | 'bold' | 'italic' = 'normal', maxWidth = 178) => {
    pdf.setFont('times', style)
    pdf.setFontSize(size)
    pdf.setTextColor(color)
    pdf.text(pdf.splitTextToSize(value, maxWidth), x, y)
  }
  const heading = (value: string, y: number) => serif(value, m, y, 19, dark, 'bold', 125)
  const eyebrow = (value: string, y: number, color = blue) => {
    pdf.setDrawColor(color)
    pdf.setLineWidth(0.7)
    pdf.line(m, y - 1.5, m + 5.3, y - 1.5)
    text(value.toUpperCase(), m + 8, y, 6.5, color, 'bold', 110)
  }
  const rect = (x: number, y: number, w: number, h: number, fill = '#FFFFFF') => {
    pdf.setDrawColor(border)
    pdf.setFillColor(fill)
    pdf.rect(x, y, w, h, 'FD')
  }
  const image = (src: string, x: number, y: number, w: number, h: number) => {
    if (!src) return
    try {
      const props = pdf.getImageProperties(src)
      const ratio = props.width / props.height
      let drawW = w
      let drawH = w / ratio
      if (drawH > h) {
        drawH = h
        drawW = h * ratio
      }
      pdf.addImage(src, src.startsWith('data:image/png') ? 'PNG' : 'JPEG', x + (w - drawW) / 2, y + (h - drawH) / 2, drawW, drawH, undefined, 'FAST')
    } catch {
      rect(x, y, w, h, '#F7FAFF')
      text('Image unavailable', x + 6, y + h / 2, 9, muted, 'normal', w - 12)
    }
  }
  const footer = (page: number, tag: string, darkMode = false) => {
    pdf.setDrawColor(darkMode ? '#1C3157' : border)
    pdf.line(0, pageH - 13, pageW, pageH - 13)
    text('KONE SalesNXT', m, pageH - 6.4, 6.2, darkMode ? '#657694' : blue, 'bold', 48)
    text(page === 1 || page === 5 ? (page === 1 ? 'Bengaluru · Mumbai · Delhi · Pan-India Network' : '© 2025 KONE India Pvt. Ltd. · Authorized Modernization Partner') : `${String(page).padStart(2, '0')} / 05`, page === 1 || page === 5 ? 70 : 98, pageH - 6.4, 6.2, darkMode ? '#566985' : muted, 'normal', 80)
    text(tag.toUpperCase(), pageW - 54, pageH - 6.4, 6.2, darkMode ? '#566985' : lightBlue, 'bold', 42)
  }
  const bigPage = (page: string, y = 28) => serif(page, pageW - 36, y, 42, pale, 'bold', 28)
  const tag = (label: string, x: number, y: number, fill: string, color: string) => {
    pdf.setFillColor(fill)
    pdf.roundedRect(x, y, 18, 5.8, 0.6, 0.6, 'F')
    text(label.toUpperCase(), x + 2, y + 4, 4.8, color, 'bold', 16)
  }
  pdf.setFillColor(dark)
  pdf.rect(0, 0, pageW, pageH, 'F')
  pdf.setFillColor(blue)
  pdf.rect(0, 0, pageW, 1.05, 'F')
  pdf.setFillColor(blue)
  pdf.rect(m, 7.8, 8, 8, 'F')
  serif('KONE SalesNXT', m + 10.5, 13.8, 11, '#FFFFFF', 'bold', 52)
  text('Modernization Proposal · 2025', pageW - 63, 13.2, 6.5, '#7889A4', 'bold', 48)
  eyebrow('Transforming Vertical Mobility', 64, cyan)
  serif('Elevate.\nEvery Floor.\nEvery Day.', m, 94, 38, '#FFFFFF', 'bold', 118)
  text('Complete elevator modernization for safer access, cleaner interfaces, improved reliability, and a more confident passenger experience.', m, 139, 11.5, '#9DAABD', 'normal', 116)
  pdf.setFillColor(blue)
  pdf.roundedRect(m, 163, 54, 13, 1.3, 1.3, 'F')
  text('Request a Site Survey', m + 5, 171, 6.8, '#FFFFFF', 'bold', 44)
  rect(146, 61, 29, 58, '#102347')
  pdf.setDrawColor('#2D5EC6')
  pdf.line(160.5, 66, 160.5, 114)
  pdf.line(146, 76, 175, 76)
  text('5F', 156.8, 72, 7, lightBlue, 'bold', 12)
  rect(148, 79, 12, 35, '#132B52')
  rect(162, 79, 11, 35, '#132B52')
  rect(177, 70, 4, 26, '#102347')
  pdf.setFillColor(blue)
  pdf.circle(179, 75, 1.1, 'F')
  pdf.circle(179, 82, 1.1, 'F')
  text('Lift System', 149, 126, 5, '#546581', 'bold', 34)
  const statY = 229
  pdf.setDrawColor('#243858')
  pdf.line(m, statY - 12, pageW - m, statY - 12)
  ;[
    ['20+', 'Years Experience', 'Modernization practice across KONE service teams'],
    ['500+', 'Lifts Modernized', 'Across residential and commercial properties'],
    ['40%', 'Energy Savings', 'Depending on selected components and usage'],
    ['24/7', 'Service Support', 'Maintenance support for critical buildings'],
  ].forEach(([num, lbl, sub], i) => {
    const sx = m + i * 45.5
    if (i) pdf.line(sx - 4, statY - 12, sx - 4, statY + 21)
    serif(num, sx + 9, statY, 24, blue, 'bold', 32)
    text(lbl.toUpperCase(), sx + 3, statY + 11, 6.3, '#9AA9BE', 'bold', 38)
    text(sub, sx + 3, statY + 18, 5.4, '#7A8AA3', 'normal', 38)
  })
  footer(1, '', true)

  pdf.addPage()
  eyebrow('The Transformation', 17)
  heading(`${primary.page2Title}\nBefore & After`, 29)
  text(primary.page2Description, m, 45, 8, muted, 'normal', 108)
  text('Customized modernization scope based on your selected components.', m, 59, 6.5, muted, 'normal', 110)
  bigPage('02', 24)
  pdf.setDrawColor(border)
  pdf.line(0, 67, pageW, 67)
  pdf.line(pageW / 2, 67, pageW / 2, 230)
  tag('Before', m, 75, '#E6EDF6', muted)
  text(`Existing ${primary.name} Condition`, m + 22, 79.4, 7.4, ink, 'bold', 66)
  rect(m, 88, 84, 115, pale2)
  image(beforeImage, m + 3, 91, 78, 109)
  text('Current Condition', m, 211, 7.5, ink, 'bold', 72)
  text('Aged finishes, outdated controls, reduced visibility, and recurring maintenance points affect the user experience.', m, 218, 7, muted, 'normal', 78)
  tag('After', 111, 75, blue, '#FFFFFF')
  text(primary.fullName, 133, 79.4, 7.4, ink, 'bold', 60)
  rect(111, 88, 84, 115, pale2)
  image(afterImage, 114, 91, 78, 109)
  text(primary.fullName, 111, 211, 7.5, ink, 'bold', 72)
  text('Final generated output from the selected modernization pipeline, shown with the corresponding component specification.', 111, 218, 7, muted, 'normal', 78)
  pdf.setFillColor(blue)
  pdf.rect(0, 236, pageW, 14, 'F')
  text(`${primary.fullName} selected for modernization`, m, 244.2, 8, '#FFFFFF', 'bold', 124)
  text(`${selectedIds.map(id => componentBrochureData[id].name).join(' · ')} reflected in this brochure.`, m, 248.5, 6.4, '#BDD0FF', 'normal', 124)
  serif(String(selectedIds.length), pageW - 31, 245, 16, '#FFFFFF', 'bold', 14)
  text('Components'.toUpperCase(), pageW - 35, 249, 5.2, '#BDD0FF', 'bold', 20)
  ;[['Passenger Experience', 'Clearer controls, indicators, finishes, and lighting improve everyday use.'], ['Serviceability', 'Modular parts and cleaner access reduce replacement time.'], ['Building Value', 'Visible modernization improves confidence in the elevator system.']].forEach(([h, b], i) => {
    const bx = i * 70
    pdf.setDrawColor(border)
    if (i) pdf.line(bx, 250, bx, 282)
    text(h.toUpperCase(), bx + 10, 260, 5.5, blue, 'bold', 50)
    text(b, bx + 10, 268, 6.5, muted, 'normal', 50)
  })
  footer(2, 'Dynamic Transformation')

  pdf.addPage()
  eyebrow('Component Reference', 17)
  heading('Core System Components', 29)
  text('Detailed component information for the modernization scope, including function, upgrade value, materials, safety notes, and maintenance benefit.', m, 45, 8, muted, 'normal', 116)
  bigPage('03', 24)
  pdf.line(0, 67, pageW, 67)
  let y = 74
  Object.values(componentBrochureData).forEach((component, index) => {
    const cx = index % 2 === 0 ? m : 108
    const cy = y + Math.floor(index / 2) * 85
    rect(cx, cy, 88, 78, '#FFFFFF')
    rect(cx, cy, 88, 13, pale)
    image(componentImages[component.id], cx + 5, cy + 18, 30, 38)
    text(component.name, cx + 38, cy + 8.5, 10.2, dark, 'bold', 45)
    text(component.fullName, cx + 38, cy + 13, 5.5, muted, 'normal', 44)
    text('Purpose', cx + 40, cy + 25, 5.3, blue, 'bold', 16)
    text(component.purpose, cx + 54, cy + 25, 4.9, muted, 'normal', 34)
    text('Upgrade', cx + 40, cy + 39, 5.3, blue, 'bold', 16)
    text(component.keyUpgrades, cx + 54, cy + 39, 4.9, muted, 'normal', 34)
    text('Safety', cx + 40, cy + 55, 5.3, blue, 'bold', 16)
    text(component.safetyCompliance, cx + 54, cy + 55, 4.9, muted, 'normal', 34)
    text('Maint.', cx + 40, cy + 70, 5.3, blue, 'bold', 16)
    text(component.maintenanceBenefit, cx + 54, cy + 70, 4.9, muted, 'normal', 34)
  })
  footer(3, 'System Components')

  pdf.addPage()
  eyebrow('Selected Scope', 17)
  heading('Door Modernization\n& Technical Specs', 29)
  text('Customized modernization scope based on your selected components.', m, 46, 8, muted, 'normal', 116)
  bigPage('04', 24)
  pdf.line(0, 67, pageW, 67)
  rect(0, 67, pageW, 15, pale)
  text('A concise technical summary for customer review, installation planning, and modernization discussion.', m, 76, 7, muted, 'normal', 160)
  pdf.line(pageW / 2, 82, pageW / 2, 280)
  y = 96
  selectedIds.map(id => componentBrochureData[id]).forEach(component => {
    text((component.fullName).toUpperCase(), m, y, 6.5, blue, 'bold', 84)
    y += 6
    component.technicalSpecs.forEach(([label, value]) => {
      pdf.setDrawColor(border)
      pdf.line(m, y, 100, y)
      text(label, m, y + 4.6, 6.2, ink, 'bold', 36)
      text(value, 50, y + 4.6, 6.2, muted, 'normal', 48)
      y += 7.3
    })
    y += 8
  })
  rect(119, 94, 62, 70, navy)
  ;[['EN 81', 'Safety aligned'], ['LED', 'Energy-efficient'], ['MOD', 'Service-friendly'], [String(selectedIds.length), 'Selected scope']].forEach(([num, lbl], i) => {
    const yy = 104 + i * 14
    pdf.setFillColor('#15386F')
    pdf.roundedRect(124, yy - 6, 17, 9, 1, 1, 'F')
    text(num, 127, yy, 7.2, '#FFFFFF', 'bold', 14)
    text(lbl, 145, yy - 0.5, 7, '#D7E2F5', 'bold', 30)
  })
  rect(119, 166, 62, 32, '#FFFFFF')
  ;['EN 81-20/50', 'EN 81-70', 'EN 81-28', 'IEC 60947', 'BIS Certified'].forEach((chip, i) => {
    rect(123 + (i % 2) * 28, 173 + Math.floor(i / 2) * 8, 24, 5, pale)
    text(chip, 125 + (i % 2) * 28, 176.7 + Math.floor(i / 2) * 8, 4.8, '#1142A8', 'bold', 20)
  })
  footer(4, 'Technical Specs')

  pdf.addPage()
  pdf.setFillColor(navy)
  pdf.rect(0, 0, pageW, pageH, 'F')
  pdf.setFillColor(blue)
  pdf.rect(0, 0, pageW, 1.05, 'F')
  serif('KONE SalesNXT', m, 15, 9, '#FFFFFF', 'bold', 52)
  text('Modernization Proposal · 2025', pageW - 67, 14, 5.5, '#70819E', 'bold', 56)
  pdf.line(0, 23, pageW, 23)
  eyebrow('Ready to Upgrade?', 43, cyan)
  serif('Your Building\nDeserves Better.', m, 66, 25, '#FFFFFF', 'bold', 120)
  text('Whether you manage a residential complex, commercial tower, hotel, hospital, or mixed-use property, elevator modernization directly affects safety, comfort, accessibility, and the way visitors experience your building.', m, 98, 8.4, '#9CA9BE', 'normal', 132)
  pdf.setFillColor(blue)
  pdf.roundedRect(m, 111, 58, 11, 1.3, 1.3, 'F')
  text('Book Free Site Survey', m + 5, 118, 6.5, '#FFFFFF', 'bold', 48)
  text('Free engineer assessment within 48 hours', m + 67, 118, 7, '#D7E2F5', 'bold', 70)
  pdf.line(0, 121, pageW, 121)
  ;[['01', 'Improved Reliability', 'A focused component upgrade can reduce visible wear, refresh critical interfaces, and support smoother daily operation.'], ['02', 'Better Passenger Experience', 'Modern controls, clear indicators, improved lighting, and refined finishes create a cleaner and more dependable ride.'], ['03', 'Long-Term Value', 'Modernize the components that matter most today while extending the useful life of the existing elevator system.']].forEach(([num, h, b], i) => {
    const bx = i * 70
    if (i) pdf.line(bx, 121, bx, 170)
    rect(bx + 14, 132, 8, 8, '#15386F')
    text(num, bx + 16, 137.3, 6, blue, 'bold', 8)
    text(h, bx + 14, 148, 8, '#FFFFFF', 'bold', 48)
    text(b, bx + 14, 157, 6.5, '#8492AA', 'normal', 48)
  })
  pdf.line(0, 170, pageW, 170)
  pdf.line(pageW / 2, 170, pageW / 2, 282)
  text('Get in Touch'.toUpperCase(), m, 188, 6, blue, 'bold', 60)
  ;[['T', '+91 98765 43210', 'Mon-Sat, 9 am - 6 pm IST'], ['M', 'sales@kone-salesnxt.in', '24 hr email response guaranteed'], ['L', 'Bengaluru · Mumbai · Delhi', 'Pan-India service & installation network'], ['W', 'www.kone.com/salesnxt', 'Online survey booking available 24/7']].forEach(([ico, h, b], i) => {
    const yy = 201 + i * 16
    text(ico, m, yy, 8, blue, 'bold', 8)
    text(h, m + 9, yy, 8, '#FFFFFF', 'bold', 78)
    text(b, m + 9, yy + 5, 6.5, '#7A889F', 'normal', 78)
  })
  text('No Obligation'.toUpperCase(), 119, 188, 6, '#71819C', 'bold', 58)
  serif('Book a Free\nSite Survey', 119, 204, 16, '#FFFFFF', 'bold', 70)
  text('Share this proposal with your facility team. Our engineers will assess the existing installation and recommend the right modernization scope.', 119, 224, 7, '#8492AA', 'normal', 70)
  text('www.kone.com/salesnxt', 119, 243, 8, '#FFFFFF', 'bold', 70)
  text('Free engineer assessment within 48 hours', 119, 252, 7, '#8FA1BD', 'normal', 70)
  pdf.setFillColor(blue)
  pdf.roundedRect(119, 264, 58, 11, 1.2, 1.2, 'F')
  text('Schedule Assessment', 124, 271.1, 6.4, '#FFFFFF', 'bold', 48)
  footer(5, '', true)

  pdf.save('elevator-modernization-brochure.pdf')
}

async function downloadAnnotatedImage(imageUrl: string, pins: ComponentPin[], labels: Record<ComponentKey, string>, filename: string) {
  const image = new Image()
  image.crossOrigin = 'anonymous'
  image.src = imageUrl
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve()
    image.onerror = () => reject(new Error('Annotated image is not available'))
  })

  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not create annotated image')

  ctx.drawImage(image, 0, 0)
  pins.forEach(pin => {
    const x = (pin.x / 100) * canvas.width
    const y = (pin.y / 100) * canvas.height
    const label = labels[pin.componentKey]
    ctx.font = '600 18px Arial'
    const labelWidth = ctx.measureText(label).width
    const boxWidth = labelWidth + 24
    const boxHeight = 30
    const boxX = Math.max(8, Math.min(canvas.width - boxWidth - 8, x + 10))
    const boxY = Math.max(8, y - boxHeight - 12)

    ctx.fillStyle = 'rgba(10,10,10,0.85)'
    ctx.fillRect(boxX, boxY, boxWidth, boxHeight)
    ctx.fillStyle = '#ffffff'
    ctx.fillText(label, boxX + 12, boxY + 21)
    ctx.beginPath()
    ctx.arc(x, y, 7, 0, Math.PI * 2)
    ctx.fillStyle = '#ffffff'
    ctx.fill()
    ctx.lineWidth = 4
    ctx.strokeStyle = 'rgba(10,10,10,0.85)'
    ctx.stroke()
  })

  downloadFromUrl(canvas.toDataURL('image/png'), filename)
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Step6Download() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, triggerRender, completeOffering, goToStep, setDownloadReady } = useOfferingStore()
  const { isGuest } = useAuthStore()
  const [rendered, setRendered] = useState(currentOffering?.renderComplete ?? false)
  const [annotationsOn, setAnnotationsOn] = useState(true)
  const [activeFilters, setActiveFilters] = useState<ComponentKey[]>(
    currentOffering?.selectedComponents ?? []
  )
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!currentOffering?.outputVideoUrl) {
      toast('Generate the video preview before opening Downloads.', 'destructive')
      goToStep(5)
      navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`, { replace: true })
      return
    }

    if (isGuest && projectId && currentOffering) {
      getGuestSessionId()
        .then(sessionId => apiClient.post('/guest/finalize', {
          is_guest: true,
          session_id: sessionId,
          project_id: projectId,
          project_name: currentOffering.name,
          video_options: {
            quality: currentOffering.videoQuality,
            motion: currentOffering.videoMotionStyle,
            speed: currentOffering.videoSpeed,
          },
        }).then(() => sessionId))
        .then(async sessionId => {
          for (;;) {
            const { data } = await apiClient.get('/guest/status', {
              params: { session_id: sessionId, project_id: projectId },
            })
            if (data.status === 'ready_for_download') {
              setDownloadUrl(data.download_url)
              setDownloadReady(data.download_url)
              setRendered(true)
              toast('Your outputs are ready to download')
              return
            }
            if (data.status === 'failed') throw new Error(data.error || 'Finalize failed')
            await new Promise(resolve => setTimeout(resolve, 1500))
          }
        })
        .catch(error => toast(error.message || 'Final files are not ready'))
      return
    }

    if (!currentOffering?.renderComplete) {
      triggerRender().then(() => {
        setRendered(true)
        toast('Your outputs are ready to download')
      })
    } else {
      setRendered(true)
    }
  }, [])

  useEffect(() => {
    if (currentOffering?.selectedComponents) {
      setActiveFilters(currentOffering.selectedComponents)
    }
  }, [currentOffering?.id])

  const handleDownload = async (url: string | null, filename: string, type: DownloadType) => {
    if (type === 'annotations') {
      const imageUrl = offering?.outputImageUrl ?? offering?.uploadedFileUrl ?? null
      if (!imageUrl) {
        toast('Output file not available yet')
        return
      }
      try {
        await downloadAnnotatedImage(imageUrl, pins, COMP_LABELS, filename)
      } catch (error) {
        toast(error instanceof Error ? error.message : 'Annotated image is not available', 'destructive')
      }
      return
    }

    if (isGuest) {
      const sessionId = await getGuestSessionId()
      const base = import.meta.env.VITE_API_BASE_URL || '/api/v1'
      const quality = currentOffering?.videoQuality ?? '1080p'
      const href = downloadUrl ?? `${base}/guest/download?session_id=${encodeURIComponent(sessionId)}&project_id=${encodeURIComponent(projectId ?? '')}`
      const separator = href.includes('?') ? '&' : '?'
      window.location.href = `${href}${separator}type=${encodeURIComponent(type)}&video_quality=${encodeURIComponent(quality)}`
      return
    }
    if (!url) {
      toast('Output file not available yet')
      return
    }
    toast(`Downloading ${filename}...`)
    downloadFromUrl(url, filename)
  }

  const handleBrochureDownload = async () => {
    if (!offering) {
      toast('Brochure data is not available yet', 'destructive')
      return
    }
    try {
      toast('Generating brochure PDF...')
      await withTimeout(generateBrochurePdf(offering), 30000, 'Brochure PDF generation timed out')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Brochure PDF could not be generated', 'destructive')
    }
  }

  const handleSave = async () => {
    await completeOffering()
    toast('Visualization saved to project')
    navigate(`/projects/${projectId}`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
    goToStep(5)
  }

  const toggleFilter = (k: ComponentKey) =>
    setActiveFilters(prev => prev.includes(k) ? prev.filter(f => f !== k) : [...prev, k])

  const pins = currentOffering?.componentPins ?? []
  const offering = currentOffering

  // ─── Loading state ───────────────────────────────────────────────────────────

  if (!rendered) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-5 rounded-2xl border border-[#E8EDF5] bg-white p-12">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[#E8EDF5] bg-[#F8FAFF]">
          <Loader2 className="animate-spin text-[#1A6AFF]" style={{ width: 22, height: 22 }} />
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold text-[#0A0A0A]">Rendering outputs</p>
          <p className="mt-1 text-xs text-[#8A9BB5]">Preparing your image, video, and brochure files</p>
        </div>
        <div className="h-px w-24 bg-gradient-to-r from-transparent via-[#D0DCF5] to-transparent" />
        <p className="text-[11px] tracking-wide text-[#B0BECE] uppercase">This usually takes a few seconds</p>
      </div>
    )
  }

  const downloads = [
    {
      icon: ImageIcon,
      title: 'Rendered Image',
      subtitle: 'High-quality composite render',
      url: isGuest ? downloadUrl : offering?.outputImageUrl ?? null,
      file: 'final_output.png',
      type: 'image' as const,
      highlight: false,
    },
    {
      icon: Layers,
      title: 'Image with Callouts',
      subtitle: 'Render with annotation overlay',
      url: isGuest ? downloadUrl : offering?.outputImageUrl ?? null,
      file: 'salesnxt-callouts.png',
      type: 'annotations' as const,
      highlight: true,
    },
    {
      icon: Video,
      title: 'Video Export',
      subtitle: `${offering?.videoQuality} · ${offering?.videoMotionStyle === 'zoom-in' ? 'Zoom In' : offering?.videoMotionStyle === 'pan-lr' ? 'Pan L–R' : 'Pan R–L'}`,
      url: isGuest ? downloadUrl : offering?.outputVideoUrl ?? null,
      file: 'elevator_animation.mp4',
      type: 'video' as const,
      highlight: false,
    },
  ]

  return (
    <div className="space-y-5">

      {/* ── Step header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={handleBack}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#E4EAF4] bg-white text-[#8A9BB5] transition-colors hover:border-[#C8D5EC] hover:text-[#4A5568]"
            aria-label="Back to previous step"
          >
            <ArrowLeft style={{ width: 14, height: 14 }} />
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#1A6AFF]">Step 6 of 6</p>
            <h2 className="text-sm font-semibold text-[#0A0A0A]">Render & Download</h2>
          </div>
        </div>
        <div className="flex items-center gap-1.5 rounded-full border border-[#D4EDDA] bg-[#F0FAF3] px-3 py-1">
          <CheckCircle2 style={{ width: 12, height: 12 }} className="text-[#2E7D52]" />
          <span className="text-[11px] font-medium text-[#2E7D52]">Render complete</span>
        </div>
      </div>

      {/* ── Main card ───────────────────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-2xl border border-[#E8EDF5] bg-white shadow-[0_1px_4px_rgba(10,30,70,0.04)]">

        {/* Downloads section */}
        <div className="border-b border-[#F0F4FA] px-8 py-6">
          <div className="mb-5 flex items-end justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8A9BB5]">Export Files</p>
              <h3 className="mt-0.5 text-sm font-semibold text-[#0A0A0A]">Download your outputs</h3>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {downloads.map(d => (
              <div
                key={d.file}
                className={cn(
                  'group relative flex flex-col gap-4 rounded-xl border p-5 transition-shadow',
                  d.highlight
                    ? 'border-[#1A6AFF] bg-[#F4F8FF] shadow-[0_0_0_1px_#1A6AFF]'
                    : 'border-[#E8EDF5] bg-white hover:border-[#C8D5EC] hover:shadow-[0_2px_8px_rgba(10,30,70,0.06)]'
                )}
              >
                {d.highlight && (
                  <span className="absolute right-3 top-3 rounded-full bg-[#1A6AFF] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                    Featured
                  </span>
                )}
                <div className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-lg border',
                  d.highlight ? 'border-[#B8CEFF] bg-[#E6EEFF]' : 'border-[#E8EDF5] bg-[#F8FAFF]'
                )}>
                  <d.icon
                    className={d.highlight ? 'text-[#1A6AFF]' : 'text-[#8A9BB5]'}
                    style={{ width: 16, height: 16 }}
                  />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-[#0A0A0A]">{d.title}</p>
                  <p className="mt-0.5 text-[11px] text-[#8A9BB5]">{d.subtitle}</p>
                </div>
                <button
                  onClick={() => handleDownload(d.url, d.file, d.type)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all',
                    d.highlight
                      ? 'bg-[#1A6AFF] text-white hover:bg-[#1558E0] shadow-[0_1px_3px_rgba(26,106,255,0.35)]'
                      : 'border border-[#E4EAF4] bg-white text-[#4A5568] hover:bg-[#F4F7FC] hover:border-[#C8D5EC]'
                  )}
                  style={{ height: 32 }}
                >
                  <Download style={{ width: 11, height: 11 }} />
                  Download
                </button>
              </div>
            ))}

            {/* Brochure card */}
            <div className="group flex flex-col gap-4 rounded-xl border border-[#E8EDF5] bg-white p-5 transition-shadow hover:border-[#C8D5EC] hover:shadow-[0_2px_8px_rgba(10,30,70,0.06)]">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#E8EDF5] bg-[#F8FAFF]">
                <FileText className="text-[#8A9BB5]" style={{ width: 16, height: 16 }} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-[#0A0A0A]">Client Brochure</p>
                <p className="mt-0.5 text-[11px] text-[#8A9BB5]">Presentation-ready PDF document</p>
              </div>
              <button
                onClick={handleBrochureDownload}
                className="flex items-center gap-1.5 rounded-lg border border-[#E4EAF4] bg-white px-3 text-xs font-semibold text-[#4A5568] transition-all hover:bg-[#F4F7FC] hover:border-[#C8D5EC]"
                style={{ height: 32 }}
              >
                <Download style={{ width: 11, height: 11 }} />
                Download Brochure
              </button>
            </div>
          </div>
        </div>

        {/* Final output previews */}
        {(offering?.outputImageUrl || offering?.outputVideoUrl) && (
          <div className="border-b border-[#F0F4FA] px-8 py-6">
            <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8A9BB5]">Output Preview</p>
            <div className="grid grid-cols-2 gap-4">
              {offering.outputImageUrl && (
                <div>
                  <p className="mb-2 text-[11px] font-medium text-[#4A5568]">Rendered Image</p>
                  <div className="overflow-hidden rounded-xl border border-[#E8EDF5] bg-[#F8FAFF]">
                    <img
                      src={offering.outputImageUrl}
                      alt="Final rendered output"
                      className="w-full object-cover"
                      style={{ maxHeight: 240 }}
                    />
                  </div>
                </div>
              )}
              {offering.outputVideoUrl && (
                <div>
                  <p className="mb-2 text-[11px] font-medium text-[#4A5568]">Video Export</p>
                  <div className="overflow-hidden rounded-xl border border-[#E8EDF5] bg-[#F8FAFF]">
                    <video
                      src={offering.outputVideoUrl}
                      controls
                      className="w-full"
                      style={{ maxHeight: 240 }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Annotated preview section */}
        <div className="px-8 py-6">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#8A9BB5]">Annotation Preview</p>
            <div className="flex items-center gap-2">
              {(offering?.selectedComponents ?? []).map(k => (
                <button
                  key={k}
                  onClick={() => toggleFilter(k)}
                  aria-pressed={activeFilters.includes(k)}
                  disabled={!annotationsOn}
                  className={cn(
                    'rounded-lg px-3 text-[11px] font-semibold transition-all disabled:opacity-40',
                    activeFilters.includes(k) && annotationsOn
                      ? 'bg-[#0A0A0A] text-white'
                      : 'border border-[#E4EAF4] bg-white text-[#4A5568] hover:bg-[#F4F7FC]'
                  )}
                  style={{ height: 28 }}
                >
                  {COMP_LABELS[k]}
                </button>
              ))}
              <button
                onClick={() => setAnnotationsOn(v => !v)}
                className="flex items-center gap-1.5 rounded-lg border border-[#E4EAF4] bg-white px-3 text-[11px] font-semibold text-[#4A5568] transition-all hover:bg-[#F4F7FC]"
                style={{ height: 28 }}
                aria-label={annotationsOn ? 'Turn annotations off' : 'Turn annotations on'}
              >
                {annotationsOn
                  ? <Eye style={{ width: 12, height: 12 }} />
                  : <EyeOff style={{ width: 12, height: 12 }} />}
                {annotationsOn ? 'Annotations on' : 'Annotations off'}
              </button>
            </div>
          </div>
          <div className="overflow-hidden rounded-xl border border-[#E8EDF5]">
            <AnnotatedPreview
              imageUrl={offering?.outputImageUrl ?? offering?.uploadedFileUrl ?? null}
              pins={pins}
              annotationsEnabled={annotationsOn}
              activeFilters={activeFilters}
              labels={COMP_LABELS}
            />
          </div>
        </div>
      </div>

      {/* ── Save / complete banner ───────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-2xl border border-[#0A0A0A] bg-[#0A0A0A]">
        <div className="flex items-start justify-between gap-6 px-8 py-6">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              {/* KONE "K" logotype mark */}
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#1A6AFF]">
                <span className="text-[11px] font-black tracking-tight text-white">K</span>
              </div>
              <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-[#4A6A9A]">KONE SalesNXT</span>
            </div>
            <h3 className="mt-3 text-base font-semibold text-white">Visualization complete</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-[#6A8AAA]">
              {isGuest
                ? 'Create a free account to save this visualization permanently and access it across sessions.'
                : 'Save this visualization to your project. You can then build a full Sales Brochure from the project screen.'}
            </p>
            {offering && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {offering.environments.map(e => (
                  <span key={e} className="rounded-md border border-[#1E3050] bg-[#111D30] px-2.5 py-1 text-[11px] font-medium capitalize text-[#8AAAD0]">
                    {e}
                  </span>
                ))}
                {offering.selectedComponents.map(k => (
                  <span key={k} className="rounded-md border border-[#1E3050] bg-[#111D30] px-2.5 py-1 text-[11px] font-medium text-[#8AAAD0]">
                    {COMP_LABELS[k]}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-3 pt-1">
            {isGuest ? (
              <Link
                to="/signup"
                className="flex items-center gap-2 rounded-xl bg-white px-5 text-sm font-semibold text-[#0A0A0A] transition-colors hover:bg-[#F0F4FF]"
                style={{ height: 40 }}
              >
                Sign up — it's free
              </Link>
            ) : (
              <button
                onClick={handleSave}
                className="flex items-center gap-2 rounded-xl bg-white px-5 text-sm font-semibold text-[#0A0A0A] transition-colors hover:bg-[#F0F4FF]"
                style={{ height: 40 }}
              >
                Save to project
              </button>
            )}
            <p className="text-[10px] text-[#3A5070]">All files remain accessible after saving</p>
          </div>
        </div>
        {/* Bottom accent bar */}
        <div className="h-0.5 bg-gradient-to-r from-[#1A6AFF] via-[#4A90FF] to-transparent" />
      </div>

    </div>
  )
}
