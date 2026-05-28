import { lazy, Suspense } from 'react'
import { createBrowserRouter, RouterProvider, Navigate, Outlet } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { useAuthStore } from '../store/authStore'

const LandingPage = lazy(() => import('../pages/landing/LandingPage'))
const SignInPage = lazy(() => import('../pages/auth/SignInPage'))
const SignUpPage = lazy(() => import('../pages/auth/SignUpPage'))
const ProjectsPage = lazy(() => import('../pages/projects/ProjectsPage'))
const ProjectDetailPage = lazy(() => import('../pages/projects/ProjectDetailPage'))
const OfferingShell = lazy(() => import('../pages/offering/OfferingShell'))
const BrochurePage = lazy(() => import('../pages/offering/brochure/BrochurePage'))

function AuthGuard() {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/signin" replace />
  return <Outlet />
}

function PublicOnlyGuard() {
  const { isAuthenticated } = useAuthStore()
  if (isAuthenticated) return <Navigate to="/projects" replace />
  return <Outlet />
}

function FullPageLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-[#F9FAFB]">
      <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-blue-700 border-t-transparent" />
    </div>
  )
}

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <Suspense fallback={<FullPageLoader />}>
        <LandingPage />
      </Suspense>
    ),
  },
  {
    element: <PublicOnlyGuard />,
    children: [
      {
        path: '/signin',
        element: <Suspense fallback={<FullPageLoader />}><SignInPage /></Suspense>,
      },
      {
        path: '/signup',
        element: <Suspense fallback={<FullPageLoader />}><SignUpPage /></Suspense>,
      },
    ],
  },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            path: '/projects',
            element: <Suspense fallback={<FullPageLoader />}><ProjectsPage /></Suspense>,
          },
          {
            path: '/projects/:projectId',
            element: <Suspense fallback={<FullPageLoader />}><ProjectDetailPage /></Suspense>,
          },
          {
            path: '/projects/:projectId/offerings/:offeringId/brochure',
            element: <Suspense fallback={<FullPageLoader />}><BrochurePage /></Suspense>,
          },
          {
            path: '/projects/:projectId/offerings/:offeringId/*',
            element: <Suspense fallback={<FullPageLoader />}><OfferingShell /></Suspense>,
          },
          {
            path: '/projects/:projectId/offerings/new',
            element: <Suspense fallback={<FullPageLoader />}><OfferingShell /></Suspense>,
          },
        ],
      },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
