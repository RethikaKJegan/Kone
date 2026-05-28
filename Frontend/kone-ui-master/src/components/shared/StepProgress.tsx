import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import { STEP_LABELS, OPTIONAL_STEPS } from '../../lib/constants'
import type { OfferingStep } from '../../types'

interface Props {
  currentStep: OfferingStep
  completedSteps: OfferingStep[]
  onStepClick?: (step: OfferingStep) => void
}

const STEPS = [1, 2, 3, 4, 5, 6] as OfferingStep[]

export function StepProgress({ currentStep, completedSteps, onStepClick }: Props) {
  return (
    <div
      role="progressbar"
      aria-valuenow={currentStep}
      aria-valuemin={1}
      aria-valuemax={6}
      aria-label="Visualization progress"
      className="px-3 py-2"
    >
      {STEPS.map((step, idx) => {
        const isCompleted = completedSteps.includes(step)
        const isCurrent = step === currentStep
        const isOptional = OPTIONAL_STEPS.includes(step)
        const isClickable = (isCompleted || isCurrent) && !!onStepClick

        return (
          <div key={step} className="relative flex items-start">
            {/* Connector line */}
            {idx > 0 && (
              <div
                className={cn('absolute w-px')}
                style={isOptional
                  ? { left: 21, top: -18, height: 36, borderLeft: '1px dashed rgba(255,255,255,0.12)', background: 'none' }
                  : {
                      left: 21, top: -18, height: 36,
                      background: completedSteps.includes(step) || isCurrent
                        ? 'rgba(20,80,245,0.5)'
                        : 'rgba(255,255,255,0.08)'
                    }
                }
              />
            )}

            <button
              onClick={() => isClickable && onStepClick!(step)}
              disabled={!isClickable}
              aria-label={`Step ${step}: ${STEP_LABELS[step]}${isCompleted ? ' (completed)' : isCurrent ? ' (current)' : ''}`}
              className={cn(
                'mb-1.5 flex w-full items-center gap-3 rounded-[6px] px-2.5 py-2 text-left transition-all duration-150',
                isCurrent
                  ? 'bg-[#1450F5]/15'
                  : isCompleted
                    ? 'hover:bg-white/[0.06] cursor-pointer'
                    : 'cursor-default',
                !isClickable && 'pointer-events-none'
              )}
            >
              {/* Circle */}
              <div
                className={cn(
                  'flex shrink-0 items-center justify-center rounded-full border font-bold transition-all duration-150',
                  isCompleted
                    ? 'border-[#1450F5] bg-[#1450F5] text-white'
                    : isCurrent
                      ? 'border-[#1450F5] bg-[#1450F5] text-white shadow-[0_0_12px_rgba(20,80,245,0.5)]'
                      : 'border-white/15 bg-transparent text-white/25'
                )}
                style={{ width: 26, height: 26, fontSize: 11 }}
              >
                {isCompleted ? <Check style={{ width: 12, height: 12 }} /> : step}
              </div>

              {/* Label */}
              <div className="min-w-0 flex-1">
                <span
                  className={cn(
                    'leading-none transition-colors duration-150',
                    isCurrent
                      ? 'font-semibold text-white'
                      : isCompleted
                        ? 'font-medium text-white/60'
                        : 'text-white/25'
                  )}
                  style={{ fontSize: 13 }}
                >
                  {STEP_LABELS[step]}
                </span>
                {isOptional && (
                  <span style={{ fontSize: 10, marginLeft: 6, color: 'rgba(255,255,255,0.2)' }}>opt.</span>
                )}
              </div>
            </button>
          </div>
        )
      })}
    </div>
  )
}
