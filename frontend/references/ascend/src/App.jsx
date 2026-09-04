import { useEffect } from 'react'
import Lenis from 'lenis'
import Planet from './Planet.jsx'

/* Inline icons — crisp, themeable, no dependency. */
const Icon = {
  workflow: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="6" height="6" rx="1.5" /><rect x="15" y="15" width="6" height="6" rx="1.5" />
      <path d="M6 9v3a3 3 0 0 0 3 3h3" />
    </svg>
  ),
  analytics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19V5" /><path d="M4 19h16" /><path d="M8 16v-4" /><path d="M13 16V8" /><path d="M18 16v-7" />
    </svg>
  ),
  leads: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" />
    </svg>
  ),
  bolt: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />
    </svg>
  ),
  globe: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z" />
    </svg>
  ),
  arrow: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
    </svg>
  ),
}

const NAV = ['Features', 'Solutions', 'Plans', 'Learning']

const LOGOS = ['Nimbus', 'Pluma', 'Citrus', 'Spider', 'Helod', 'Vertx']

const FEATURES = [
  { icon: Icon.workflow, title: 'Clever workflows', body: 'Automate every hand-off with visual, branching pipelines that move deals forward while you sleep.' },
  { icon: Icon.analytics, title: 'Live analytics', body: 'Real-time dashboards turn raw funnel data into the one number that tells you what to do next.' },
  { icon: Icon.leads, title: 'Seamless leads', body: 'Capture, score, and route every lead automatically — no spreadsheet, no leak, no lag.' },
  { icon: Icon.bolt, title: 'Instant triggers', body: 'Fire actions across your stack the moment intent appears, in milliseconds not minutes.' },
  { icon: Icon.shield, title: 'Enterprise-grade', body: 'SOC 2, SSO, and granular roles baked in — security that scales quietly with your team.' },
  { icon: Icon.globe, title: 'Global by default', body: 'Multi-region, multi-currency, and low-latency everywhere your customers happen to be.' },
]

const STATS = [
  { value: '3.4×', label: 'Faster pipeline velocity' },
  { value: '92%', label: 'Lead capture accuracy' },
  { value: '11k+', label: 'Teams scaling on Ascend' },
  { value: '$2.1B', label: 'Revenue influenced' },
]

// helper: per-element stagger delay as a CSS custom property
const rd = (ms) => ({ '--rd': `${ms}ms` })

export default function App() {
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // ---- Lenis smooth scroll ----
    let lenis, raf
    if (!reduce) {
      lenis = new Lenis({ duration: 1.15, smoothWheel: true, touchMultiplier: 1.5 })
      const loop = (t) => { lenis.raf(t); raf = requestAnimationFrame(loop) }
      raf = requestAnimationFrame(loop)
    }

    // ---- staggered scroll reveal ----
    const els = document.querySelectorAll('[data-reveal]')
    if (reduce) {
      els.forEach((el) => el.classList.add('in'))
      return () => {}
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
        })
      },
      { threshold: 0.18, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((el) => io.observe(el))

    return () => { cancelAnimationFrame(raf); lenis?.destroy(); io.disconnect() }
  }, [])

  return (
    <div className="page" id="top">
      <Planet />

      {/* ───────────── SECTION 1 · HERO ───────────── */}
      <header className="hero">
        <nav className="nav">
          <a className="brand" href="#top">
            <span className="brand-mark" aria-hidden="true">▲</span> Ascend
          </a>
          <ul className="nav-links">
            {NAV.map((item) => (
              <li key={item}><a href={`#${item.toLowerCase()}`}>{item}</a></li>
            ))}
          </ul>
          <a className="btn btn-ghost nav-cta" href="#cta">Sign Up</a>
        </nav>

        <div className="hero-inner">
          <h1 className="hero-title" data-reveal style={rd(60)}>
            Scale Smarter,<br />Not <em>Harder</em>
          </h1>
          <p className="hero-sub" data-reveal style={rd(180)}>
            Drive your funnel forward with clever workflows, analytics,
            and seamless lead management — all in one immersive command center.
          </p>
          <div className="hero-actions" data-reveal style={rd(300)}>
            <a className="btn btn-primary" href="#cta">Start Free Right Now {Icon.arrow}</a>
            <a className="btn btn-outline" href="#cta">Schedule a Consult</a>
          </div>
        </div>

        <div className="logos" data-reveal style={rd(420)}>
          <span className="logos-label">Trusted by fast-moving teams</span>
          <div className="logos-row">
            {LOGOS.map((l) => <span key={l} className="logo">{l}</span>)}
          </div>
        </div>
      </header>

      {/* ───────────── SECTION 2 · FEATURES ───────────── */}
      <section className="section features" id="features">
        <div className="section-head">
          <span className="eyebrow" data-reveal>Everything in orbit</span>
          <h2 data-reveal style={rd(80)}>One platform to run the entire revenue engine</h2>
          <p data-reveal style={rd(160)}>Stop stitching tools together. Ascend unifies capture, automation, and insight into a single surface your whole team actually enjoys using.</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f, i) => (
            <article className="card" key={f.title} data-reveal style={rd(i * 90)}>
              <span className="card-icon">{f.icon}</span>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ───────────── SECTION 3 · STATS / SHOWCASE ───────────── */}
      <section className="section showcase" id="solutions">
        <div className="showcase-grid">
          <div className="showcase-copy">
            <span className="eyebrow" data-reveal>Built for momentum</span>
            <h2 data-reveal style={rd(90)}>See the whole funnel move in real time</h2>
            <p data-reveal style={rd(180)}>Every stage, every signal, every dollar — rendered live. Ascend gives operators the altitude to spot what's working and the controls to double down instantly.</p>
            <a className="btn btn-primary" href="#cta" data-reveal style={rd(270)}>Explore the platform {Icon.arrow}</a>
          </div>

          <div className="dashboard" data-reveal style={rd(160)} aria-hidden="true">
            <div className="dash-top">
              <span className="dash-title">Pipeline · Q3</span>
              <span className="dash-live"><span className="pill-dot" /> Live</span>
            </div>
            <div className="dash-bars">
              {[62, 88, 47, 95, 71, 80, 58].map((h, i) => (
                <span key={i} className="dash-bar" style={{ '--h': `${h}%`, '--d': `${i * 90}ms` }} />
              ))}
            </div>
            <div className="dash-rows">
              {['New leads', 'Qualified', 'In negotiation', 'Closed won'].map((r, i) => (
                <div className="dash-row" key={r}>
                  <span>{r}</span>
                  <span className="dash-track"><span className="dash-fill" style={{ '--w': `${[90, 72, 48, 34][i]}%` }} /></span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="stats">
          {STATS.map((s, i) => (
            <div className="stat" key={s.label} data-reveal style={rd(i * 80)}>
              <span className="stat-value">{s.value}</span>
              <span className="stat-label">{s.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ───────────── SECTION 4 · CTA + FOOTER ───────────── */}
      <section className="section cta" id="cta">
        <div className="cta-card" data-reveal>
          <span className="eyebrow" data-reveal style={rd(60)}>Ready when you are</span>
          <h2 data-reveal style={rd(140)}>Put your growth on a new trajectory</h2>
          <p data-reveal style={rd(220)}>Launch in minutes. No credit card. Cancel anytime. Join thousands of teams compounding revenue on Ascend.</p>
          <div className="hero-actions" data-reveal style={rd(300)}>
            <a className="btn btn-primary" href="#top">Start Free Right Now {Icon.arrow}</a>
            <a className="btn btn-outline" href="#top">Talk to Sales</a>
          </div>
        </div>

        <footer className="footer" data-reveal>
          <div className="footer-brand">
            <a className="brand" href="#top"><span className="brand-mark" aria-hidden="true">▲</span> Ascend</a>
            <p>The revenue command center for ambitious teams.</p>
          </div>
          <div className="footer-cols">
            <div><h4>Product</h4><a href="#features">Features</a><a href="#solutions">Solutions</a><a href="#cta">Plans</a></div>
            <div><h4>Company</h4><a href="#top">About</a><a href="#top">Careers</a><a href="#top">Blog</a></div>
            <div><h4>Legal</h4><a href="#top">Privacy</a><a href="#top">Terms</a><a href="#top">Security</a></div>
          </div>
        </footer>
        <div className="copyright">© {new Date().getFullYear()} Ascend, Inc. — Built among the stars.</div>
      </section>
    </div>
  )
}
