import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../hooks/useToast'
import axios from 'axios'

const schema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
})
type FormData = z.infer<typeof schema>

export default function SignInPage() {
  const [showPw, setShowPw] = useState(false)
  const { signIn, continueAsGuest } = useAuthStore()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    try {
      await signIn(data.email, data.password)
      navigate('/projects')
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        setError('password', { message: 'Incorrect email or password' })
      } else {
        setError('password', { message: 'Something went wrong. Try again.' })
      }
    }
  }

  const handleGuest = () => {
    continueAsGuest()
    navigate('/projects')
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F5F6F8] px-4 py-12">

      {/* Logo */}
      <div className="mb-8 text-center">
        <span className="text-heading text-[22px] font-extrabold tracking-tight text-[#1450F5]">KONE</span>
        <span className="ml-2 text-[13px] font-medium text-[#9CA3AF]">SalesNXT</span>
      </div>

      <div
        className="w-full max-w-[400px] overflow-hidden rounded-2xl bg-white px-8 py-9"
        style={{ boxShadow: '0 4px 24px -4px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.05)' }}
      >
        <h1 className="text-heading text-[22px] font-bold tracking-tight text-[#111827]">Welcome back</h1>
        <p className="mt-1 text-[13px] text-[#9CA3AF]">Sign in with your KONE account to continue.</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-7 space-y-5" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="email" className="label-caps block">Email</label>
            <input
              id="email"
              type="email"
              {...register('email')}
              autoComplete="email"
              placeholder="you@kone.com"
              className="field-input w-full rounded-lg border border-[#E4E4E4] bg-[#FAFAFA] px-3.5 text-[#111827] transition-all duration-[150ms]"
              style={{ height: 42 }}
            />
            {errors.email && <p className="text-[12px] text-red-500">{errors.email.message}</p>}
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="label-caps block">Password</label>
              <button
                type="button"
                className="text-[11px] font-medium text-[#6B7280] transition-colors duration-[120ms] hover:text-[#1450F5]"
                onClick={() => toast('Password reset is managed by your KONE IT administrator')}
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <input
                id="password"
                type={showPw ? 'text' : 'password'}
                {...register('password')}
                autoComplete="current-password"
                placeholder="••••••••"
                className="field-input w-full rounded-lg border border-[#E4E4E4] bg-[#FAFAFA] px-3.5 pr-10 text-[#111827] transition-all duration-[150ms]"
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
            {errors.password && <p className="text-[12px] text-red-500">{errors.password.message}</p>}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#1450F5] text-[13px] font-semibold text-white transition-all duration-[150ms] hover:bg-[#1040D0] hover:shadow-md hover:shadow-[#1450F5]/20 disabled:opacity-50"
            style={{ height: 42 }}
          >
            {isSubmitting && <Loader2 style={{ width: 15, height: 15 }} className="animate-spin" />}
            Sign in
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
          Don't have an account?{' '}
          <Link to="/signup" className="font-semibold text-[#1450F5] transition-colors duration-[120ms] hover:text-[#1040D0]">
            Sign up
          </Link>
        </p>

        <p className="mt-2 text-center text-[11px] text-[#D1D5DB]">
          Single sign-on available for enterprise accounts
        </p>
      </div>

      <div className="mt-7 flex w-full max-w-[400px] items-center justify-between text-[11px] text-[#C4C9D4]">
        <span>&copy; 2026 KONE Corporation. All rights reserved.</span>
        <span>SalesNXT v1.0</span>
      </div>
    </div>
  )
}
