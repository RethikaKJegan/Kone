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
  const [guestLoading, setGuestLoading] = useState(false)
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
      if (axios.isAxiosError(err) && [400, 401].includes(err.response?.status ?? 0)) {
        setError('password', { message: 'Incorrect email or password' })
      } else {
        setError('password', { message: 'Something went wrong. Try again.' })
      }
    }
  }

  const handleGuest = async () => {
    setGuestLoading(true)
    try {
      await continueAsGuest()
      navigate('/projects')
    } catch {
      setError('password', { message: 'Guest login failed. Try again.' })
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

      <div className="w-full max-w-[380px] rounded-lg border border-[#E4E4E4] bg-white p-8">
        <h1 className="text-xl font-semibold text-[#0A0A0A]">Sign in</h1>
        <p className="mt-1 text-sm text-[#A3A3A3]">Use your KONE account credentials to continue.</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <div className="space-y-1">
            <label htmlFor="email" className="block text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
              Email
            </label>
            <input
              id="email"
              type="email"
              {...register('email')}
              autoComplete="email"
              className={inputClass}
              style={{ height: 36 }}
              placeholder="you@kone.com"
            />
            {errors.email && <p className="text-xs text-red-600">{errors.email.message}</p>}
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="block text-[11px] font-medium uppercase tracking-[0.05em] text-[#6B7280]">
                Password
              </label>
              <button
                type="button"
                className="text-xs text-[#525252] transition-colors duration-[120ms] hover:text-[#0A0A0A]"
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
                className={inputClass + ' pr-10'}
                style={{ height: 36 }}
                placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
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
            {errors.password && <p className="text-xs text-red-600">{errors.password.message}</p>}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-[5px] bg-[#0A0A0A] py-0 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626] disabled:opacity-50"
            style={{ height: 34 }}
          >
            {isSubmitting && <Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />}
            Sign in
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
          Don't have an account?{' '}
          <Link to="/signup" className="font-medium text-[#0A0A0A] transition-colors duration-[120ms] hover:text-[#525252]">
            Sign up
          </Link>
        </p>

        <p className="mt-3 text-center text-[11px] text-[#C8C8C8]">
          Single sign-on available for enterprise accounts
        </p>
      </div>

      <div className="mt-6 flex w-full max-w-[380px] items-center justify-between text-[11px] text-[#C8C8C8]">
        <span>&copy; 2026 KONE Corporation. All rights reserved.</span>
        <span>SalesNXT v1.0</span>
      </div>
    </div>
  )
}
