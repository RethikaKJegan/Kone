import { useEffect } from 'react'
import { ToastProvider, ToastViewport, Toast, ToastTitle, ToastClose } from './toast'
import { useToastState, registerToast } from '../../hooks/useToast'

export function Toaster() {
  const { toasts, addToast, removeToast } = useToastState()

  useEffect(() => {
    registerToast(addToast)
  }, [addToast])

  return (
    <ToastProvider>
      {toasts.map(t => (
        <Toast key={t.id} variant={t.variant} open onOpenChange={open => !open && removeToast(t.id)}>
          <ToastTitle>{t.title}</ToastTitle>
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  )
}
