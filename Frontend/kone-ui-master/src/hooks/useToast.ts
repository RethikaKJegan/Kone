import { useState, useCallback } from 'react'

interface ToastItem {
  id: string
  title: string
  variant?: 'default' | 'destructive'
}

let toastFn: ((title: string, variant?: 'default' | 'destructive') => void) | null = null

export function registerToast(fn: typeof toastFn) {
  toastFn = fn
}

export function toast(title: string, variant: 'default' | 'destructive' = 'default') {
  toastFn?.(title, variant)
}

export function useToastState() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((title: string, variant: 'default' | 'destructive' = 'default') => {
    const id = `${Date.now()}`
    setToasts(prev => [...prev, { id, title, variant }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return { toasts, addToast, removeToast }
}
