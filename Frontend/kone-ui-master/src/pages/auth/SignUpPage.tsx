import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { cn } from '../../lib/utils'
import axios from 'axios'

const schema = z
  .object({
    name: z.string().min(2, 'Name must be at least 2 characters'),
    email: z.string().email('Enter a valid email address'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string(),
  })
  .refine(d => d.password === d.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })
type FormData = z.infer<typeof schema>

function passwordStrength(pw: string): { label: string; level: number; color: string } {
  if (pw.length === 0) return { label: '', level: 0, color: '' }
  let score = 0
  if (pw.length >= 8) score++
  if (pw.length >= 12) score++
  if (/[A-Z]/.test(pw) && /[0-9]/.test(pw)) score++
  if (/[^A-Za-z0-9]/.test(pw)) score++
  const levels = [
    { label: 'Weak', color: 'bg-red-400' },
    { label: 'Fair', color: 'bg-amber-400' },
    { label: 'Strong', color: 'bg-[#10B981]' },
    { label: 'Very strong', color: 'bg-[#10B981]' },
  ]
  return { ...levels[Math.min(score, 3)], level: score + 1 }
}

export default function SignUpPage() {
  const [showPw, setShowPw] = useState(false)
  const { signUp, continueAsGuest } = useAuthStore()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const pw = watch('password', '')
  const strength = passwordStrength(pw)

  const onSubmit = async (data: FormData) => {
    try {
      await signUp(data.name, data.email, data.password)
      navigate('/projects')
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        setError('email', { message: 'An account with this email already exists' })
      } else {
        setError('email', { message: 'Something went wrong. Try again.' })
      }
    }
  }

  const handleGuest = () => {
    continueAsGuest()
    navigate('/projects')
  }

  const inputClass =
    'field-input w-full rounded-lg border border-[#E4E4E4] bg-[#FAFAFA] px-3.5 text-[#111827] transition-all duration-[150ms]'

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F5F6F8] px-4 py-12">

      {/* Logo */}
      <div className="mb-8 text-center">
        <span className="text-heading text-[22px] font-extrabold tracking-tight text-[#1450F5]">KONE</span>
        <span className="ml-2 text-[13px] font-medium text-[#9CA3AF]">SalesNXT</span>
      </div>

      <div
        className="w-full max-w-[460px] overflow-hidden rounded-2xl bg-white px-8 py-9"
        style={{ boxShadow: '0 4px 24px -4px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.05)' }}
      >
        <h1 className="text-heading text-[22px] font-bold tracking-tight text-[#111827]">Create your account</h1>
        <p className="mt-1 text-[13px] text-[#9CA3AF]">Join your KONE team on SalesNXT</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-7 space-y-5" noValidate>
          {[
            { id: 'name', label: 'Full Name', type: 'text', placeholder: 'Pavan Kumar', autoComplete: 'name' },
            { id: 'email', label: 'Work Email', type: 'email', placeholder: 'you@kone.com', autoComplete: 'email' },
          ].map(field => (
            <div key={field.id} className="space-y-1.5">
              <label htmlFor={field.id} className="label-caps block">{field.label}</label>
              <input
                id={field.id}
                type={field.type}
                {...register(field.id as keyof FormData)}
                autoComplete={field.autoComplete}
                placeholder={field.placeholder}
                className={inputClass}
                style={{ height: 42 }}
              />
              {errors[field.id as keyof FormData] && (
                <p className="text-[12px] text-red-500">{errors[field.id as keyof FormData]?.message}</p>
              )}
            </div>
          ))}

          <div className="space-y-1.5">
            <label htmlFor="password" className="label-caps block">Password</label>
            <div className="relative">
              <input
                id="password"
                type={showPw ? 'text' : 'password'}
                {...register('password')}
                autoComplete="new-password"
                placeholder="Min. 8 characters"
                className={inputClass + ' pr-10'}
                style={{ height: 42 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#C4C9D4] transition-colors duration-[120ms] hover:text-[#6B7280]"
              >
                {showPw ? <EyeOff style={{ width: 16, height: 16 }} /> : <Eye style={{ width: 16, height: 16 }} />}
              </button>
            </div>
            {pw.length > 0 && (
              <div className="mt-2 space-y-1">
                <div className="flex gap-1">
                  {[1, 2, 3, 4].map(lvl => (
                    <div
                      key={lvl}
                      className={cn(
                        'h-[3px] flex-1 rounded-full transition-colors duration-[150ms]',
                        lvl <= strength.level ? strength.color : 'bg-[#E9ECEF]'
                      )}
                    />
                  ))}
                </div>
                <p className="text-[11px] font-medium text-[#9CA3AF]">{strength.label}</p>
              </div>
            )}
            {errors.password && <p className="text-[12px] text-red-500">{errors.password.message}</p>}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="confirmPassword" className="label-caps block">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              {...register('confirmPassword')}
              autoComplete="new-password"
              placeholder="••••••••"
              className={inputClass}
              style={{ height: 42 }}
            />
            {errors.confirmPassword && (
              <p className="text-[12px] text-red-500">{errors.confirmPassword.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#1450F5] text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20 disabled:opacity-50"
            style={{ height: 42 }}
          >
            {isSubmitting && <Loader2 style={{ width: 15, height: 15 }} className="animate-spin" />}
            Create account
          </button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[#F0F0F0]" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-white px-3 text-[11px] font-medium text-[#C4C9D4]">or</span>
          </div>
        </div>

        <button
          onClick={handleGuest}
          className="flex w-full items-center justify-center rounded-lg border border-[#E4E4E4] bg-white text-[13px] font-semibold text-[#374151] transition-all duration-[150ms] hover:border-[#D1D5DB] hover:bg-[#F9FAFB]"
          style={{ height: 42 }}
        >
          Continue as guest
        </button>

        <p className="mt-6 text-center text-[12px] text-[#9CA3AF]">
          Already have an account?{' '}
          <Link to="/signin" className="font-semibold text-[#1450F5] transition-colors duration-[120ms] hover:text-[#1040D0]">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
