'use client'

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Button } from '@/components/ui/button'
import { PressScale } from '@/lib/motion-primitives'
import { usePlatformPresets } from '../hooks/use-platform-presets'
import {
  ROOM_PLATFORMS,
  PLATFORM_LABELS,
  PLATFORM_ACCENT,
  asScoringFormat,
  asRosterFormat,
  isRoomPlatform,
  type RoomPlatform
} from '../utils/platform-presets'
import type { DraftConfig } from '@/lib/nfl/types'

interface MockDraftSetupDialogProps {
  config: DraftConfig
  onConfigChange: (config: DraftConfig) => void
  onStartMock: (overrides?: Partial<DraftConfig>) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

const TIMER_OPTIONS: Array<{ label: string; value: number | null }> = [
  { label: 'Off', value: null },
  { label: '15s', value: 15 },
  { label: '30s', value: 30 },
  { label: '60s', value: 60 },
  { label: '90s', value: 90 }
]

const ADP_SOURCE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Consensus ADP (FantasyPros-style, via FFC)', value: 'ffc' },
  { label: 'ESPN ADP', value: 'espn' }
]

/** Default rankings source for a platform preset — espn maps to ESPN ADP, everything else to consensus (FFC). */
function defaultAdpSource(presetAdpSource: string | undefined): string {
  return presetAdpSource === 'espn' ? 'espn' : 'ffc'
}

/**
 * Mock draft setup — the flow the toolbar "Mock Draft" button opens (never
 * instant-starts a mock with hidden defaults). Everything that shapes a mock
 * session lives here: draft room style, teams, the user's own pick slot
 * (previously missing from the flow entirely), scoring/roster, pick clock,
 * and rankings (ADP) source.
 */
export function MockDraftSetupDialog({
  config,
  onConfigChange,
  onStartMock,
  open,
  onOpenChange
}: MockDraftSetupDialogProps) {
  const presets = usePlatformPresets()
  const [randomSlot, setRandomSlot] = useState(false)

  function update<K extends keyof DraftConfig>(key: K, value: DraftConfig[K]) {
    onConfigChange({ ...config, [key]: value })
  }

  const activePlatform: RoomPlatform = isRoomPlatform(config.platform) ? config.platform : 'custom'
  const isLocked = activePlatform !== 'custom'
  const activePreset = presets[activePlatform]

  function handlePlatformChange(next: string) {
    if (!next || !isRoomPlatform(next)) return
    if (next === 'custom') {
      onConfigChange({ ...config, platform: 'custom' })
      return
    }
    const preset = presets[next]
    const scoring = asScoringFormat(preset.scoring_format)
    const rosterFormat = asRosterFormat(preset.roster_format)
    onConfigChange({
      ...config,
      platform: next,
      ...(scoring ? { scoring } : {}),
      ...(rosterFormat ? { roster_format: rosterFormat } : {}),
      timer_seconds: preset.timer_seconds ?? null,
      adp_source: defaultAdpSource(preset.adp_source)
    })
  }

  const teamCounts = [8, 10, 12, 14]
  const slots = Array.from({ length: config.n_teams }, (_, i) => i + 1)
  const effectiveTimer = config.timer_seconds !== undefined ? config.timer_seconds : activePreset.timer_seconds
  const effectiveAdpSource = config.adp_source ?? defaultAdpSource(activePreset.adp_source)

  function handleStart() {
    const overrides: Partial<DraftConfig> = {}
    if (randomSlot) {
      overrides.user_pick = Math.floor(Math.random() * config.n_teams) + 1
    }
    onStartMock(overrides)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Mock Draft Setup</DialogTitle>
        </DialogHeader>

        <div className='space-y-[var(--gap-stack)] py-[var(--space-2)]'>
          {/* Draft room style */}
          <div className='space-y-[var(--space-2)]'>
            <label className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Draft room style
            </label>
            <ToggleGroup
              type='single'
              variant='outline'
              value={activePlatform}
              onValueChange={handlePlatformChange}
              className='w-full'
            >
              {ROOM_PLATFORMS.map(p => (
                <ToggleGroupItem
                  key={p}
                  value={p}
                  aria-label={`${PLATFORM_LABELS[p]} draft room style`}
                  style={activePlatform === p ? { color: PLATFORM_ACCENT[p], borderColor: PLATFORM_ACCENT[p] } : undefined}
                >
                  {PLATFORM_LABELS[p]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {isLocked ? (
              <div className='flex items-center justify-between gap-[var(--space-2)]'>
                <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  Locked to {PLATFORM_LABELS[activePlatform]} style — scoring and roster
                  format are pre-filled to match.
                </p>
                <Button variant='ghost' size='sm' onClick={() => handlePlatformChange('custom')}>
                  Unlock to customize
                </Button>
              </div>
            ) : (
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Custom — scoring and roster format are yours to set.
              </p>
            )}
          </div>

          {/* Teams */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='mock-teams-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Teams
            </label>
            <Select
              value={String(config.n_teams)}
              onValueChange={v => {
                const n = Number(v)
                update('n_teams', n)
                if (config.user_pick > n) update('user_pick', n)
              }}
            >
              <SelectTrigger id='mock-teams-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {teamCounts.map(n => (
                  <SelectItem key={n} value={String(n)}>
                    {n} teams
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Your pick slot -- prominent: this was completely missing before. */}
          <div className='space-y-[var(--space-2)] rounded-md border p-[var(--space-3)]'>
            <label htmlFor='mock-slot-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Your pick slot
            </label>
            <Select
              value={randomSlot ? 'random' : String(config.user_pick)}
              onValueChange={v => {
                if (v === 'random') {
                  setRandomSlot(true)
                  return
                }
                setRandomSlot(false)
                update('user_pick', Number(v))
              }}
            >
              <SelectTrigger id='mock-slot-select' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='random'>Random</SelectItem>
                {slots.map(p => (
                  <SelectItem key={p} value={String(p)}>
                    Pick #{p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              {randomSlot
                ? 'A slot is randomly assigned when the draft starts.'
                : `You draft #${config.user_pick} overall.`}
            </p>
          </div>

          {/* Scoring */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='mock-scoring-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Scoring
            </label>
            <Select
              value={config.scoring}
              onValueChange={v => update('scoring', v as DraftConfig['scoring'])}
              disabled={isLocked}
            >
              <SelectTrigger id='mock-scoring-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='ppr'>PPR</SelectItem>
                <SelectItem value='half_ppr'>Half-PPR</SelectItem>
                <SelectItem value='standard'>Standard</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Roster Format */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='mock-rosterformat-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Roster Format
            </label>
            <Select
              value={config.roster_format}
              onValueChange={v => update('roster_format', v as DraftConfig['roster_format'])}
              disabled={isLocked}
            >
              <SelectTrigger id='mock-rosterformat-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='standard'>Standard</SelectItem>
                <SelectItem value='superflex'>Superflex</SelectItem>
                <SelectItem value='2qb'>2QB</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Pick clock -- defaults from the platform preset, always editable */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='mock-timer-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Pick clock
            </label>
            <Select
              value={effectiveTimer ? String(effectiveTimer) : 'off'}
              onValueChange={v => update('timer_seconds', v === 'off' ? null : Number(v))}
            >
              <SelectTrigger id='mock-timer-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIMER_OPTIONS.map(opt => (
                  <SelectItem key={opt.label} value={opt.value == null ? 'off' : String(opt.value)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Rankings (ADP) source */}
          <div className='space-y-[var(--space-2)]'>
            <label htmlFor='mock-adp-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Rankings (ADP) source
            </label>
            <Select value={effectiveAdpSource} onValueChange={v => update('adp_source', v)}>
              <SelectTrigger id='mock-adp-select' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADP_SOURCE_OPTIONS.map(opt => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <PressScale className='w-full'>
            <Button className='w-full' onClick={handleStart}>
              Start Mock Draft
            </Button>
          </PressScale>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
