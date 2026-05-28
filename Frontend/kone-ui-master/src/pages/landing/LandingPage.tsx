import { useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

// ── Keyframes + interactive CSS ──────────────────────────────────────────────
const STYLES = `
  /* ── Core Variables & Organic Theme ── */
  :root {
    --scroll-y: 0;
  }

  /* ── Cinematic Text Reveals ── */
  .snx-reveal-mask {
    overflow: hidden;
    display: inline-flex;
    vertical-align: top;
  }
  .snx-reveal-text {
    display: inline-block;
    transform: translateY(110%) rotate(2deg);
    opacity: 0;
    animation: snx-slide-up 0.9s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  @keyframes snx-slide-up {
    0% { transform: translateY(110%) rotate(2deg); opacity: 0; }
    100% { transform: translateY(0) rotate(0); opacity: 1; }
  }

  /* ── Staggered Delays ── */
  .delay-100 { animation-delay: 100ms; }
  .delay-200 { animation-delay: 200ms; }
  .delay-300 { animation-delay: 300ms; }

  /* ── Organic Blobs ── */
  @keyframes snx-blob-flow {
    0% { transform: translate(0, 0) scale(1) rotate(0deg); }
    33% { transform: translate(40px, -60px) scale(1.1) rotate(15deg); }
    66% { transform: translate(-30px, 30px) scale(0.9) rotate(-10deg); }
    100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  }

  /* ── Fade & Zoom ── */
  @keyframes snx-fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes snx-zoom-in-soft {
    from { opacity: 0; transform: scale(0.96) translateY(10px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
  }

  /* ── Interactive Pill ── */
  .snx-glass-pill {
    background: rgba(255, 255, 255, 0.45);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.8);
    box-shadow: 0 4px 24px -6px rgba(0,0,0,0.06), inset 0 0 0 1px rgba(255,255,255,0.4);
    animation: snx-fade-in 1s ease forwards;
  }
  .snx-glass-pill::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent);
    background-size: 200% 100%;
    animation: pill-shimmer 3s infinite linear;
    pointer-events: none;
    mix-blend-mode: overlay;
  }
  @keyframes pill-shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* ── Scroll reveal ── */
  @keyframes snx-reveal {
    from { opacity: 0; transform: translateY(24px) scale(0.96); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }
  [data-reveal] { opacity: 0; }
  [data-reveal][data-vis] {
    animation: snx-reveal 0.7s cubic-bezier(0.22,1,0.36,1) both;
  }

  /* ── Navbar blur on scroll ── */
  .snx-nav {
    transition: background 0.3s, border-color 0.3s, backdrop-filter 0.3s;
  }
  .snx-nav-scrolled {
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    background: rgba(255,255,255,0.75) !important;
    border-bottom-color: rgba(0,0,0,0.06) !important;
  }

  /* ── CTAs ── */
  .snx-nav-btn { transition: background 0.15s, transform 0.2s cubic-bezier(0.22,1,0.36,1); }
  .snx-nav-btn:hover { background: #1A1A1A !important; transform: scale(1.03); }
  
  .snx-cta-dark { transition: all 0.2s cubic-bezier(0.22,1,0.36,1); }
  .snx-cta-dark:hover { background: #1A1A1A !important; transform: scale(1.03) translateY(-1px); box-shadow: 0 10px 25px -10px rgba(0,0,0,0.4); }
  
  .snx-cta-outline { transition: all 0.2s cubic-bezier(0.22,1,0.36,1); }
  .snx-cta-outline:hover {
    background: rgba(255,255,255,0.9) !important;
    border-color: #D1D5DB !important;
    transform: scale(1.03) translateY(-1px);
    box-shadow: 0 10px 25px -10px rgba(0,0,0,0.1);
  }

  /* ── Cards ── */
  .snx-bento-card {
    transition: all 0.4s cubic-bezier(0.16,1,0.3,1);
    cursor: default;
  }
  .snx-bento-card:hover {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(255,255,255,0.15) !important;
    transform: translateY(-4px);
    box-shadow: 0 20px 40px -10px rgba(0,0,0,0.5);
    z-index: 1;
  }
  
  /* ── Architectural Matrix Cards ── */
  .snx-arch-card {
    transition: background 0.4s ease;
    cursor: default;
  }
  .snx-arch-card:hover {
    background: #F8FAFC !important;
  }
  .snx-arch-card:hover .arch-num {
    transform: translateY(-10px) scale(1.02);
    color: #F1F5F9 !important;
  }
  
  .snx-feat {
    position: relative;
    transition: all 0.3s cubic-bezier(0.22,1,0.36,1);
    cursor: default;
  }
  .snx-feat:hover {
    background: #FFFFFF !important;
    box-shadow: 0 20px 40px -15px rgba(0,0,0,0.08), inset 0 0 0 1px rgba(0,0,0,0.05);
    transform: translateY(-4px);
    z-index: 1;
  }
  .snx-step-card {
    transition: transform 0.5s cubic-bezier(0.22,1,0.36,1), opacity 0.5s, box-shadow 0.4s;
    transform-origin: center top;
  }
  .snx-step-card:hover {
    transform: translateY(-6px) !important;
    box-shadow: 0 24px 50px -15px rgba(0,0,0,0.1) !important;
    border-color: #E5E7EB !important;
  }
`

// ── Data ─────────────────────────────────────────────────────────────────────
const features = [
  { num: '01', title: 'AI Placement',           desc: 'Upload any building photo and let spatial intelligence position components automatically.' },
  { num: '02', title: 'Component Visualisation', desc: 'See exactly how Ceiling, COP, LCI, and Door components look in the real environment.' },
  { num: '03', title: 'Annotated Preview',       desc: 'Generate labelled previews with per-component callouts, togglable on the fly.' },
  { num: '04', title: 'Video Export',            desc: 'Render cinematic zoom or pan videos from your static composite at up to 1080p.' },
  { num: '05', title: 'Sales Brochure',          desc: 'Build a client-ready PDF brochure combining your renders with structured sales copy.' },
  { num: '06', title: 'Project Management',      desc: 'Organise multiple client projects and offerings in one workspace.' },
]

const steps = [
  { n: '01', title: 'Upload',            desc: 'Upload your building photo or video to get started.' },
  { n: '02', title: 'Select & AI Place', desc: 'Select KONE components and let AI position them precisely.' },
  { n: '03', title: 'Export',            desc: 'Export renders, video, and a complete sales brochure.' },
]

// ── Scroll reveal hook ───────────────────────────────────────────────────────
function useScrollReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('[data-reveal]')
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const delay = Number((entry.target as HTMLElement).dataset.delay ?? 0)
            setTimeout(() => entry.target.setAttribute('data-vis', 'true'), delay)
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.1, rootMargin: '0px 0px -32px 0px' }
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate        = useNavigate()
  const continueAsGuest = useAuthStore((s) => s.continueAsGuest)
  const handleGuest     = () => { continueAsGuest(); navigate('/projects') }
  const navRef          = useRef<HTMLElement>(null)

  useScrollReveal()

  // Scroll handlers for navbar, global parallax, and 3D progress
  useEffect(() => {
    const handler = () => {
      const sy = window.scrollY
      navRef.current?.classList.toggle('snx-nav-scrolled', sy > 24)
      document.documentElement.style.setProperty('--scroll-y', String(sy))
      
      // Calculate progress from 0 to 1 based on first 800px of scroll
      const progress = Math.min(Math.max(sy / 800, 0), 1)
      document.documentElement.style.setProperty('--scroll-progress', String(progress))
    }
    // Initialize
    handler()
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  return (
    <>
      <style>{STYLES}</style>
      <div style={{ minHeight: '100vh', background: '#FFFFFF', fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif' }}>

        {/* ── Navbar ───────────────────────────────────────────────────────── */}
        <nav
          ref={navRef}
          className="snx-nav sticky top-0 z-40 flex items-center justify-between border-b border-[#F3F4F6] px-10"
          style={{ height: 56, background: 'white' }}
        >
          <div className="flex items-center gap-3">
            <span style={{ fontWeight: 800, fontSize: 15, color: '#1450F5', letterSpacing: '-0.01em' }}>KONE</span>
            <div style={{ width: 1, height: 16, background: '#E5E7EB', flexShrink: 0 }} />
            <span style={{ fontWeight: 400, fontSize: 15, color: '#6B7280' }}>SalesNXT</span>
          </div>
          <div className="flex items-center gap-4">
            <Link to="/signin" style={{ fontWeight: 500, fontSize: 14, color: '#374151', textDecoration: 'none', transition: 'color 0.13s' }}
              onMouseEnter={e => (e.currentTarget.style.color = '#0A0A0A')}
              onMouseLeave={e => (e.currentTarget.style.color = '#374151')}
            >
              Sign in
            </Link>
            <Link to="/signup" className="snx-nav-btn"
              style={{ fontWeight: 500, fontSize: 14, padding: '8px 20px', borderRadius: 6, background: '#0A0A0A', color: '#FFFFFF', textDecoration: 'none' }}
            >
              Get started
            </Link>
          </div>
        </nav>

        {/* ── Hero — 10K Photorealistic Interactive ────────────────────────── */}
        <section style={{ 
          position: 'relative', overflow: 'hidden', 
          background: '#0a0a0a',
          paddingTop: 180, paddingBottom: 160,
          perspective: '1200px' // For 3D scroll effect
        }}>
          {/* Photorealistic Background & Animated Blobs */}
          <div aria-hidden style={{ 
            position: 'absolute', inset: -100, zIndex: 0,
            overflow: 'hidden',
            transform: 'translateY(calc(var(--scroll-y) * 0.4px)) scale(calc(1 + (var(--scroll-progress) * 0.35)))',
            willChange: 'transform'
          }}>
            <div style={{
              position: 'absolute', inset: 0,
              backgroundImage: 'url(/hero-bg.png)',
              backgroundSize: 'cover', backgroundPosition: 'center',
              opacity: 0.4,
              filter: 'brightness(0.7) contrast(1.1)',
            }} />
            
            {/* Animated Blobs mixed with the background */}
            <div style={{
              position: 'absolute', width: 800, height: 800, borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(20,80,245,0.25) 0%, rgba(26,111,212,0) 70%)',
              top: '-15%', left: '-5%',
              animation: 'snx-blob-flow 20s ease-in-out infinite alternate',
              filter: 'blur(60px)',
              mixBlendMode: 'screen'
            }} />
            <div style={{
              position: 'absolute', width: 900, height: 900, borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(56,189,248,0.15) 0%, rgba(56,189,248,0) 70%)',
              top: '5%', right: '-15%',
              animation: 'snx-blob-flow 25s ease-in-out infinite alternate-reverse',
              filter: 'blur(80px)',
              mixBlendMode: 'screen'
            }} />
          </div>
          
          {/* Gradient Overlay for Text Readability */}
          <div aria-hidden style={{
            position: 'absolute', inset: 0, zIndex: 0,
            background: 'linear-gradient(to bottom, rgba(10,10,10,0.2) 0%, rgba(10,10,10,1) 100%)'
          }} />

          {/* ── Content ──────────────────────────────────────────────────── */}
          <div style={{
            position: 'relative', zIndex: 1,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            textAlign: 'center', padding: '0 40px',
            transform: 'translateY(calc(var(--scroll-y) * -0.2px)) opacity(calc(1 - var(--scroll-progress) * 1.5))',
            opacity: 'calc(1 - (var(--scroll-progress) * 2))'
          }}>
            
            {/* Cinematic H1 */}
            <h1 style={{
              fontFamily: '"Outfit", sans-serif',
              fontSize: 'clamp(56px, 8vw, 96px)', fontWeight: 800, lineHeight: 1.05,
              letterSpacing: '-0.02em', color: '#FFFFFF',
              maxWidth: 1000, margin: 0,
              textShadow: '0 10px 30px rgba(0,0,0,0.5)'
            }}>
              <span className="snx-reveal-mask">
                <span className="snx-reveal-text delay-100">Visualise <span style={{ color: '#1450F5' }}>KONE</span></span>
              </span>
              <br />
              <span className="snx-reveal-mask">
                <span className="snx-reveal-text delay-200" style={{ color: '#94A3B8' }}>solutions instantly.</span>
              </span>
            </h1>

            {/* Subheading */}
            <p style={{
              animation: 'snx-zoom-in-soft 1s cubic-bezier(0.16,1,0.3,1) 600ms forwards',
              opacity: 0,
              fontSize: 'clamp(18px, 2vw, 24px)', fontWeight: 400, lineHeight: 1.6,
              color: '#CBD5E1', maxWidth: 640, marginTop: 32,
            }}>
              Bring spaces to life. AI-powered spatial intelligence for KONE professionals.
            </p>

            {/* CTAs */}
            <div style={{
              animation: 'snx-zoom-in-soft 1s cubic-bezier(0.16,1,0.3,1) 800ms forwards',
              opacity: 0,
              display: 'flex', alignItems: 'center', gap: 16, marginTop: 56,
            }}>
              <Link to="/signup" className="snx-cta-dark"
                style={{
                  fontWeight: 600, fontSize: 16, padding: '18px 40px', borderRadius: 12,
                  background: '#FFFFFF', color: '#0A0A0A', textDecoration: 'none', display: 'inline-block',
                }}
              >
                Start building
              </Link>
              <button onClick={handleGuest} className="snx-cta-outline"
                style={{
                  fontWeight: 600, fontSize: 16, padding: '18px 40px', borderRadius: 12,
                  background: 'rgba(255,255,255,0.05)', backdropFilter: 'blur(10px)', color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.2)', cursor: 'pointer',
                }}
              >
                View demo
              </button>
            </div>
          </div>

        </section>

        {/* ── Features — Architectural Matrix ──────────────────────────── */}
        <section style={{ background: '#FFFFFF', padding: '160px 40px', position: 'relative' }}>
          <div className="mx-auto" style={{ maxWidth: 1200 }}>
            <div style={{ 
              display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 80,
              '@media (min-width: 768px)': { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' }
            } as any}>
              <div>
                <p data-reveal data-delay="0" style={{
                  fontFamily: '"Outfit", sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: '0.15em',
                  textTransform: 'uppercase', color: '#64748B', marginBottom: 16,
                }}>
                  Core Capabilities
                </p>
                <h2 data-reveal data-delay="80" style={{
                  fontFamily: '"Outfit", sans-serif', fontSize: 'clamp(36px, 5vw, 64px)', fontWeight: 800, letterSpacing: '-0.03em',
                  color: '#0F172A', margin: 0, lineHeight: 1.05, maxWidth: 640
                }}>
                  Engineered for precision.
                </h2>
              </div>
              <p data-reveal data-delay="160" style={{ fontSize: 18, color: '#475569', maxWidth: 440, margin: 0, paddingBottom: 8, lineHeight: 1.6 }}>
                Everything required to transform a raw building photo into a winning technical proposal, instantly.
              </p>
            </div>
            
            {/* The Matrix Grid */}
            <div style={{ 
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              borderTop: '1px solid #E2E8F0', borderLeft: '1px solid #E2E8F0',
            }}>
              {features.map((f, i) => (
                <div
                  key={f.num}
                  className="snx-arch-card"
                  data-reveal
                  data-delay={String(i * 50 + 100)}
                  style={{ 
                    position: 'relative', overflow: 'hidden',
                    padding: '56px 40px',
                    borderRight: '1px solid #E2E8F0', borderBottom: '1px solid #E2E8F0',
                    background: '#FFFFFF',
                  }}
                >
                  {/* Watermark Number */}
                  <div style={{
                    position: 'absolute', right: -10, bottom: -24,
                    fontFamily: '"Outfit", sans-serif', fontSize: 200, fontWeight: 800,
                    color: '#F8FAFC', lineHeight: 1, zIndex: 0,
                    transition: 'transform 0.6s cubic-bezier(0.16,1,0.3,1), color 0.4s ease'
                  }} className="arch-num">
                    {f.num}
                  </div>
                  
                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <div style={{ width: 16, height: 16, background: '#0F172A', marginBottom: 40 }} />
                    <h3 style={{ fontFamily: '"Outfit", sans-serif', fontSize: 24, fontWeight: 700, color: '#0F172A', marginBottom: 16, letterSpacing: '-0.01em' }}>{f.title}</h3>
                    <p style={{ fontSize: 16, lineHeight: 1.7, color: '#475569' }}>{f.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── How it works — Glassmorphic Scrollytelling ──────────────────── */}
        <section style={{ 
          position: 'relative', background: '#020617', 
          backgroundImage: 'url(/abstract-bg.png)', backgroundAttachment: 'fixed',
          backgroundSize: 'cover', backgroundPosition: 'center'
        }}>
          {/* Overlay to dim background */}
          <div aria-hidden style={{ position: 'absolute', inset: 0, background: 'rgba(2,6,23,0.75)', backdropFilter: 'blur(8px)' }} />

          <div className="mx-auto" style={{ maxWidth: 1000, position: 'relative', zIndex: 1, padding: '160px 40px' }}>
            <p data-reveal data-delay="0" style={{
              fontFamily: '"Outfit", sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: '0.15em',
              textTransform: 'uppercase', color: '#1450F5', textAlign: 'center', marginBottom: 16,
            }}>
              Workflow
            </p>
            <h2 data-reveal data-delay="80" style={{
              fontFamily: '"Outfit", sans-serif', fontSize: 'clamp(36px, 5vw, 56px)', fontWeight: 800, letterSpacing: '-0.03em',
              color: '#FFFFFF', textAlign: 'center', marginBottom: 100, textShadow: '0 10px 30px rgba(0,0,0,0.8)'
            }}>
              From photo to proposal<br/>in three steps.
            </h2>

            <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 60, paddingBottom: 100 }}>
              {/* Connecting glowing line */}
              <div style={{
                position: 'absolute', top: 40, bottom: 40, left: 40, width: 2,
                background: 'linear-gradient(to bottom, transparent, rgba(20,80,245,0.6), transparent)',
                zIndex: 0
              }} />

              {steps.map((s, i) => (
                <div key={s.n} data-reveal data-delay="0" style={{
                  display: 'flex', gap: 48, alignItems: 'center',
                  background: 'rgba(15,23,42,0.6)', padding: 48, borderRadius: 32,
                  boxShadow: '0 30px 60px -15px rgba(0,0,0,0.5), 0 0 0 1px #082062 inset',
                  backdropFilter: 'blur(24px)',
                  position: 'sticky', top: 120 + i * 30, // Creates 3D stacking effect
                  zIndex: i + 1,
                  transition: 'transform 0.4s cubic-bezier(0.16,1,0.3,1)'
                }}>
                  <div style={{
                    width: 80, height: 80, borderRadius: '50%',
                    background: 'linear-gradient(135deg, rgba(20,80,245,0.25) 0%, rgba(20,80,245,0.08) 100%)',
                    border: '1px solid rgba(20,80,245,0.5)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, position: 'relative', zIndex: 2,
                    boxShadow: '0 0 40px rgba(20,80,245,0.25) inset'
                  }}>
                    <span style={{ fontFamily: '"Outfit", sans-serif', fontSize: 32, fontWeight: 700, color: '#FFFFFF' }}>{s.n}</span>
                  </div>
                  <div>
                    <h3 style={{ fontFamily: '"Outfit", sans-serif', fontSize: 32, fontWeight: 700, color: '#F8FAFC', marginBottom: 16, letterSpacing: '-0.02em' }}>{s.title}</h3>
                    <p style={{ fontSize: 18, color: '#CBD5E1', lineHeight: 1.6, maxWidth: 500 }}>{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Cinematic CTA strip ──────────────────────────────────────────── */}
        <section data-reveal data-delay="0" style={{ 
          position: 'relative', overflow: 'hidden',
          background: '#000000', padding: '140px 40px', textAlign: 'center' 
        }}>
          {/* Radial glow */}
          <div aria-hidden style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            width: '80%', height: '80%', background: 'radial-gradient(circle, rgba(56,189,248,0.1) 0%, transparent 60%)',
            pointerEvents: 'none'
          }} />

          <div style={{ position: 'relative', zIndex: 1 }}>
            <h2 style={{ fontFamily: '"Outfit", sans-serif', fontSize: 'clamp(36px, 4vw, 56px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#FFFFFF', margin: 0 }}>
              Ready to win more projects?
            </h2>
            <p style={{ fontSize: 20, color: '#94A3B8', marginTop: 24, marginBottom: 48, maxWidth: 600, marginInline: 'auto', lineHeight: 1.6 }}>
              Experience the future of elevator sales visualisation. No complex setups, just stunning results in seconds.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
              <Link to="/signup" className="snx-cta-dark"
                style={{
                  fontWeight: 600, fontSize: 16, padding: '18px 40px', borderRadius: 12,
                  background: '#FFFFFF', color: '#0A0A0A', textDecoration: 'none', display: 'inline-block',
                }}
              >
                Start building
              </Link>
              <button onClick={handleGuest} className="snx-cta-outline"
                style={{
                  fontWeight: 600, fontSize: 16, padding: '18px 40px', borderRadius: 12,
                  background: 'rgba(255,255,255,0.05)', color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.2)', cursor: 'pointer',
                  backdropFilter: 'blur(10px)'
                }}
              >
                View live demo
              </button>
            </div>
          </div>
        </section>

        {/* ── Footer ───────────────────────────────────────────────────────── */}
        <footer className="flex items-center justify-between"
          style={{ background: '#000000', padding: '40px', borderTop: '1px solid rgba(255,255,255,0.1)' }}
        >
          <div>
            <p style={{ fontFamily: '"Outfit", sans-serif', fontWeight: 700, fontSize: 16, letterSpacing: '0.05em' }}>
              <span style={{ color: '#1450F5' }}>KONE</span>
              <span style={{ color: '#FFFFFF' }}> SalesNXT</span>
            </p>
            <p style={{ fontSize: 14, color: '#64748B', marginTop: 8 }}>
              &copy; 2026 KONE Corporation. All rights reserved.
            </p>
          </div>
          <p style={{ fontFamily: '"Outfit", sans-serif', fontSize: 14, color: '#475569', fontWeight: 600 }}>SalesNXT v1.0</p>
        </footer>

      </div>
    </>
  )
}
