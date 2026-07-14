import type { Metadata } from 'next';
import Link from 'next/link';
import { Gx01Body } from '@/components/gx01';
import { Scorebug } from '@/components/nfl/scorebug';

export const metadata: Metadata = {
  title: 'GIQ — We beat the consensus. Here’s the receipt.',
  description:
    'NFL fantasy projections and game predictions graded against the industry consensus across 11,000+ player-weeks — misses published too.'
};

/**
 * Marketing home — sketch 001-B "Broadcast Overlay" winner. The scorebug IS
 * the hero on a pitch-green field gradient; apple-style one-idea-per-screen
 * sections follow. Accuracy claims are the REAL 2025 numbers (v4.3 audit:
 * QB −0.39 / WR −0.075 / TE −0.43 vs Sleeper consensus; RB +0.26 shown
 * honestly as WIP). Static-first: no backend calls on this page.
 */

const NAV_ITEMS = [
  { label: 'Draft Room', href: '/dashboard/draft' },
  { label: 'Rankings', href: '/dashboard/rankings' },
  { label: 'Scores', href: '/dashboard/predictions' },
  { label: 'News', href: '/dashboard/news' },
  { label: 'Matchups', href: '/dashboard/matchups' },
  { label: 'My League', href: '/dashboard/leagues' }
] as const;

const RECEIPTS = [
  { num: '−0.39', label: 'QB · MAE vs consensus', win: true },
  { num: '−0.075', label: 'WR · MAE vs consensus', win: true },
  { num: '−0.43', label: 'TE · MAE vs consensus', win: true },
  { num: '+0.26', label: 'RB · we’re working on it', win: false }
] as const;

/* Stability-gated UC3 correlation edges — real values from the shipped
 * correlation network (PR #41). */
const CORRELATIONS = [
  { pair: 'MAHOMES ↔ KELCE', rho: '+0.50', n: '123 gms' },
  { pair: 'GOFF ↔ ST. BROWN', rho: '+0.51', n: '79 gms' },
  { pair: 'BURROW ↔ CHASE', rho: '+0.46', n: '63 gms' },
  { pair: 'HURTS ↔ SMITH', rho: '+0.34', n: '74 gms' }
] as const;

function SectionKicker({ children }: { children: React.ReactNode }) {
  return (
    <div className='wc-display mb-3 text-sm tracking-[0.2em] text-[var(--wc-yellow,#ffd84d)]'>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className='wc-display text-[clamp(28px,3.8vw,46px)] font-extrabold leading-[1.1] tracking-[0.04em] text-white'>
      {children}
    </h2>
  );
}

function SectionSub({ children }: { children: React.ReactNode }) {
  return (
    <p className='mx-auto mt-4 max-w-[640px] text-lg leading-relaxed text-[#9aa3b8]'>
      {children}
    </p>
  );
}

export default function MarketingHome() {
  return (
    <div className='min-h-screen bg-[#0b0e18] text-white'>
      {/* Broadcast nav — near-black bar, 2px mint rule (sketch 001-B). */}
      <nav className='sticky top-0 z-50 flex h-[52px] items-center gap-6 overflow-x-auto border-b-2 border-[var(--wc-mint,#91edd0)] bg-[var(--wc-bar,#05070d)] px-7'>
        <Link
          href='/'
          className='wc-display mr-3 whitespace-nowrap text-2xl font-extrabold tracking-[0.14em] text-white'
        >
          G<span className='text-[var(--wc-mint,#91edd0)]'>IQ</span>
        </Link>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className='wc-display whitespace-nowrap text-[15px] tracking-[0.1em] text-[#cfd6e4] transition-colors hover:text-[var(--wc-mint,#91edd0)]'
          >
            {item.label}
          </Link>
        ))}
        <span className='flex-1' />
        <Link
          href='/dashboard'
          className='wc-display hidden whitespace-nowrap rounded-full bg-[var(--wc-peri,#5b67c7)] px-4 py-1 text-[13px] tracking-[0.1em] text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)] sm:block'
        >
          Open App
        </Link>
      </nav>

      <main>
      {/* Hero — field gradient, yard lines, scorebug as the hero object. */}
      <section className='wc-hero-field relative flex min-h-[74vh] flex-col items-center justify-center overflow-hidden px-5 py-16'>
        {['18%', '33%', '48%', '63%', '78%', '93%'].map((top) => (
          <div key={top} className='wc-yard-line' style={{ top }} />
        ))}
        <h1 className='wc-display relative z-[2] text-center text-[clamp(38px,5.5vw,72px)] font-extrabold leading-[1.05] tracking-[0.03em] text-white [text-shadow:0_4px_24px_rgba(0,0,0,0.5)]'>
          We beat the consensus.
          <br />
          <span className='text-[var(--wc-yellow,#ffd84d)]'>Here’s the receipt.</span>
        </h1>
        <p className='relative z-[2] mt-3 text-center text-lg text-[#e6eaf2]'>
          Graded against Sleeper across 11,000+ player-weeks — misses published too.
        </p>

        <div className='relative z-[2] mt-16 hidden md:block'>
          <Scorebug
            awayTeam='KC'
            homeTeam='BUF'
            awayScore={27}
            homeScore={24}
            clockTab={'OUR LINE  KC −2.5'}
            detail={['Wk 1 · SNF', 'Edge: High']}
            ribbon='see every prediction →'
            ribbonHref='/dashboard/predictions'
          />
        </div>
        <div className='relative z-[2] mt-10 md:hidden'>
          <Scorebug
            compact
            awayTeam='KC'
            homeTeam='BUF'
            awayScore={27}
            homeScore={24}
            detail={['Wk 1', 'Edge High']}
          />
        </div>

        <div className='relative z-[2] mt-14 flex flex-wrap justify-center gap-3'>
          {RECEIPTS.map((r) => (
            <div
              key={r.label}
              className='min-w-[118px] rounded-[10px] border border-[rgba(145,237,208,0.45)] bg-[rgba(5,7,13,0.85)] px-5 py-2.5 text-center'
            >
              <div
                className={`wc-display text-[26px] font-extrabold ${
                  r.win ? 'text-[var(--wc-mint,#91edd0)]' : 'text-[#9aa3b8]'
                }`}
              >
                {r.num}
              </div>
              <div className='wc-display mt-0.5 text-xs tracking-[0.12em] text-[#cfd6e4]'>
                {r.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Graph intelligence — real stability-gated correlation edges. */}
      <section className='border-t border-white/10 bg-[#0b0e18] px-6 py-24 text-center'>
        <SectionKicker>Graph Intelligence</SectionKicker>
        <SectionTitle>
          We model the connections
          <br />
          between players.
        </SectionTitle>
        <SectionSub>
          121 stability-gated correlations mined from a decade of games — every edge held
          its sign across a 2016–22 training window AND a 2023–25 holdout. Know whose big
          games arrive together.
        </SectionSub>
        <div className='mt-10 flex flex-wrap justify-center gap-3.5'>
          {CORRELATIONS.map((c) => (
            <span
              key={c.pair}
              className='wc-display inline-flex items-center gap-2 rounded-full border border-white/10 bg-[#131722] px-4 py-2 text-[16px] tracking-[0.05em] transition-transform hover:-translate-y-0.5'
            >
              {c.pair}{' '}
              <b className='font-extrabold text-[var(--wc-pos,#0eaf7d)]'>{c.rho}</b>
              <span className='text-xs opacity-60'>{c.n}</span>
            </span>
          ))}
        </div>
        <p className='mt-7 text-sm text-[#9aa3b8]'>
          7,559 candidate pairs in. 121 served. The rest didn’t survive the stability
          gate.
        </p>
      </section>

      {/* Draft room. */}
      <section className='border-t border-white/10 bg-[#070a12] px-6 py-24 text-center'>
        <SectionKicker>Draft Room</SectionKicker>
        <SectionTitle>A co-pilot on the clock.</SectionTitle>
        <SectionSub>
          Live Sleeper draft sync, stack-aware recommendations, and a sleeper board built
          from vacated-opportunity graph signal — players the consensus doesn’t even
          rank.
        </SectionSub>
        <div className='mt-9'>
          <Link
            href='/dashboard/draft'
            className='inline-block rounded-full bg-[var(--wc-peri,#5b67c7)] px-7 py-3 font-semibold text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)]'
          >
            Enter the draft room
          </Link>
        </div>
      </section>

      {/* GX-01. */}
      <section className='border-t border-white/10 bg-[#0b0e18] px-6 py-24 text-center'>
        <SectionKicker>AI Advisor</SectionKicker>
        <SectionTitle>Meet GX-01.</SectionTitle>
        <SectionSub>
          Your always-on analyst — every projection, correlation, injury report and
          betting edge, one question away, on every page.
        </SectionSub>
        <div className='mt-10 flex flex-wrap items-center justify-center gap-11'>
          <Gx01Body className='scale-110' />
          <div className='w-[340px] rounded-[14px] border border-white/10 bg-[#131722] p-5 text-left text-[14.5px]'>
            <div className='mb-2.5 text-[#9aa3b8]'>
              “Start St. Brown or Chase this week?”
            </div>
            <div className='leading-relaxed text-[#e6eaf2]'>
              <b className='text-[var(--wc-yellow,#ffd84d)]'>GX-01:</b> St. Brown.
              Detroit’s implied total is 3.5 higher, his target share is trending up 4
              straight weeks, and the Goff stack correlation (+0.51) raises his ceiling
              in a projected shootout.
            </div>
          </div>
        </div>
      </section>

      {/* Predictions row — compact bugs, the system component in the wild. */}
      <section className='border-t border-white/10 bg-[#070a12] px-6 py-24 text-center'>
        <SectionKicker>Game Predictions</SectionKicker>
        <SectionTitle>
          Our line vs their line.
          <br />
          Every game, graded.
        </SectionTitle>
        <SectionSub>
          An ensemble model with calibrated cover probabilities — edges flagged when we
          disagree with the market, closing-line value tracked all season.
        </SectionSub>
        <div className='mt-12 flex flex-wrap justify-center gap-x-10 gap-y-8'>
          <Scorebug compact awayTeam='DET' homeTeam='KC' awayScore={31} homeScore={27} detail={['Edge', 'High']} />
          <Scorebug compact awayTeam='CIN' homeTeam='BUF' awayScore={24} homeScore={21} detail={['Edge', 'Med']} />
          <Scorebug compact awayTeam='PHI' homeTeam='DAL' awayScore={28} homeScore={20} detail={['Edge', 'High']} />
        </div>
        <div className='mt-10'>
          <Link
            href='/dashboard/predictions'
            className='wc-display text-[15px] tracking-[0.12em] text-[var(--wc-mint,#91edd0)] hover:underline'
          >
            See the full slate →
          </Link>
        </div>
      </section>

      {/* League sync. */}
      <section className='border-t border-white/10 bg-[#0b0e18] px-6 py-24 text-center'>
        <SectionKicker>My League</SectionKicker>
        <SectionTitle>
          Synced to your league
          <br />
          in one click.
        </SectionTitle>
        <SectionSub>
          Connect Sleeper and every ranking, projection and alert re-scores to YOUR
          scoring settings — optimal lineups, drop candidates, and waiver targets for
          your exact roster.
        </SectionSub>
        <div className='mt-9'>
          <Link
            href='/dashboard/leagues'
            className='inline-block rounded-full bg-[var(--wc-peri,#5b67c7)] px-7 py-3 font-semibold text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)]'
          >
            Connect your league
          </Link>
        </div>
        <p className='mt-6 text-sm text-[#9aa3b8]'>
          Free this season. Premium tiers arrive later — early users keep the good stuff.
        </p>
      </section>

      </main>

      <footer className='border-t border-white/10 bg-[var(--wc-bar,#05070d)] px-6 py-10 text-center'>
        <div className='wc-display text-xl font-extrabold tracking-[0.14em] text-white'>
          G<span className='text-[var(--wc-mint,#91edd0)]'>IQ</span>
        </div>
        <p className='mt-2 text-xs text-[#8892ad]'>
          Every pick graded against the closing line. Misses stay on the board — that’s
          the point.
        </p>
      </footer>
    </div>
  );
}
