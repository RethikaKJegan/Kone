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
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .regex(/[A-Za-z]/, 'Password must contain at least one letter')
      .regex(/\d/, 'Password must contain at least one number'),
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
    { label: 'Weak', color: 'bg-red-500' },
    { label: 'Fair', color: 'bg-amber-500' },
    { label: 'Strong', color: 'bg-[#16A34A]' },
    { label: 'Very strong', color: 'bg-[#16A34A]' },
  ]
  return { ...levels[Math.min(score, 3)], level: score + 1 }
}

export default function SignUpPage() {
  const [showPw, setShowPw] = useState(false)
  const [guestLoading, setGuestLoading] = useState(false)
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
      if (axios.isAxiosError(err) && [400, 409].includes(err.response?.status ?? 0)) {
        setError('email', { message: 'An account with this email already exists' })
      } else {
        setError('email', { message: 'Something went wrong. Try again.' })
      }
    }
  }

  const handleGuest = async () => {
    setGuestLoading(true)
    try {
      await continueAsGuest()
      navigate('/projects')
    } catch {
      setError('email', { message: 'Guest login failed. Try again.' })
    } finally {
      setGuestLoading(false)
    }
  }

  const inputClass = 'w-full rounded-[5px] border border-[#E4E4E4] bg-white px-3 text-sm text-[#0A0A0A] outline-none transition-colors duration-[120ms] focus:border-[#0A0A0A] focus:ring-1 focus:ring-[#0A0A0A]'

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F7F7F7] px-4 py-12">
      <div className="mb-8 text-center">
        <span className="text-xl font-bold text-[#1450F5]">KONE</span>
        <span className="ml-2 text-sm text-[#A3A3A3]">SalesNXT</span>
      </div>

      <div className="w-full max-w-[440px] rounded-lg border border-[#E4E4E4] bg-white p-8">
        <h1 className="text-xl font-semibold text-[#0A0A0A]">Create your account</h1>
        <p className="mt-1 text-sm text-[#A3A3A3]">Join your KONE team on SalesNXT</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          {[
            { id: 'name', label: 'Full Name', type: 'text', placeholder: 'Pavan Kumar', autoComplete: 'name' },
            { id: 'email', label: 'Email', type: 'email', placeholder: 'you@kone.com', autoComplete: 'email' },
          ].map(field => (
            <div key={field.id} className="space-y-1">
              <label htmlFor={field.id} className="block text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
                {field.label}
              </label>
              <input
                id={field.id}
                type={field.type}
                {...register(field.id as keyof FormData)}
                autoComplete={field.autoComplete}
                placeholder={field.placeholder}
                className={inputClass}
                style={{ height: 36 }}
              />
              {errors[field.id as keyof FormData] && (
                <p className="text-xs text-red-600">{errors[field.id as keyof FormData]?.message}</p>
              )}
            </div>
          ))}

          <div className="space-y-1">
            <label htmlFor="password" className="block text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPw ? 'text' : 'password'}
                {...register('password')}
                autoComplete="new-password"
                placeholder="Min. 8 characters"
                className={inputClass + ' pr-10'}
                style={{ height: 36 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]"
              >
                {showPw ? <EyeOff style={{ width: 15, height: 15 }} /> : <Eye style={{ width: 15, height: 15 }} />}
              </button>
            </div>
            {pw.length > 0 && (
              <div className="mt-1.5 space-y-1">
                <div className="flex gap-1">
                  {[1, 2, 3, 4].map(lvl => (
                    <div
                      key={lvl}
                      className={cn(
                        'flex-1 rounded-sm transition-colors duration-[120ms]',
                        lvl <= strength.level ? strength.color : 'bg-[#E4E4E4]'
                      )}
                      style={{ height: 3 }}
                    />
                  ))}
                </div>
                <p className="text-[11px] text-[#A3A3A3]">{strength.label}</p>
              </div>
            )}
            {errors.password && <p className="text-xs text-red-600">{errors.password.message}</p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="confirmPassword" className="block text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              {...register('confirmPassword')}
              autoComplete="new-password"
              placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
              className={inputClass}
              style={{ height: 36 }}
            />
            {errors.confirmPassword && (
              <p className="text-xs text-red-600">{errors.confirmPassword.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-[5px] bg-[#0A0A0A] text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626] disabled:opacity-50"
            style={{ height: 34 }}
          >
            {isSubmitting && <Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />}
            Create account
          </button>
        </form>

        <div className="relative my-5">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[#E4E4E4]" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-white px-3 text-xs text-[#A3A3A3]">or</span>
          </div>
        </div>

        <button
          onClick={handleGuest}
          disabled={guestLoading || isSubmitting}
          className="flex w-full items-center justify-center gap-2 rounded-[5px] border border-[#E4E4E4] text-sm font-medium text-[#525252] transition-colors duration-[120ms] hover:bg-[#F7F7F7] disabled:opacity-50"
          style={{ height: 34 }}
        >
          {guestLoading && <Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />}
          Continue as guest
        </button>

        <p className="mt-5 text-center text-xs text-[#A3A3A3]">
          Already have an account?{' '}
          <Link to="/signin" className="font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:text-[#525252]">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
