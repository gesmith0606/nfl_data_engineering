'use client'

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
  ROSTER_FORMAT_OPTIONS,
  type RoomPlatform
} from '../utils/platform-presets'
import { DraftStrategyToggle } from './draft-strategy-toggle'
import type { DraftConfig, DraftStrategy } from '@/lib/nfl/types'

interface DraftConfigDialogProps {
  config: DraftConfig
  onConfigChange: (config: DraftConfig) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  onNewDraft: () => void
}

/**
 * Manual-board settings only (scoring/roster/teams/season). Mock draft has
 * its own dedicated setup flow (`MockDraftSetupDialog`) with slot/timer/
 * rankings selection, so this dialog no longer starts a mock -- that avoids
 * a second "start mock with hidden defaults" path.
 */
export function DraftConfigDialog({
  config,
  onConfigChange,
  open,
  onOpenChange,
  onNewDraft
}: DraftConfigDialogProps) {
  const presets = usePlatformPresets()

  function update<K extends keyof DraftConfig>(key: K, value: DraftConfig[K]) {
    onConfigChange({ ...config, [key]: value })
  }

  const activePlatform: RoomPlatform = isRoomPlatform(config.platform) ? config.platform : 'custom'
  const activePreset = presets[activePlatform]

  // Nothing is ever disabled: editing a preset-controlled field flips the
  // room style to Custom while keeping the edit (matches the mock setup).
  function updateAndUnlock<K extends keyof DraftConfig>(key: K, value: DraftConfig[K]) {
    if (activePlatform !== 'custom') {
      onConfigChange({ ...config, [key]: value, platform: 'custom' })
    } else {
      update(key, value)
    }
  }

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
      ...(rosterFormat ? { roster_format: rosterFormat } : {})
    })
  }

  const teamCounts = [8, 10, 12, 14]
  const picks = Array.from({ length: config.n_teams }, (_, i) => i + 1)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Draft Settings</DialogTitle>
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
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              {activePlatform !== 'custom'
                ? `${PLATFORM_LABELS[activePlatform]} presets applied — change anything below; edits switch you to Custom.`
                : 'Custom — every setting is yours.'}
            </p>
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              {activePreset.rounds} rounds · {activePreset.timer_seconds}s pick clock
            </p>
          </div>

          {/* Teams */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='teams-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
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
              <SelectTrigger id='teams-select' className='w-32'>
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

          {/* My Pick */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='mypick-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              My Pick
            </label>
            <Select
              value={String(config.user_pick)}
              onValueChange={v => update('user_pick', Number(v))}
            >
              <SelectTrigger id='mypick-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {picks.map(p => (
                  <SelectItem key={p} value={String(p)}>
                    Pick #{p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Scoring */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='scoring-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Scoring
            </label>
            <Select
              value={config.scoring}
              onValueChange={v => updateAndUnlock('scoring', v as DraftConfig['scoring'])}
            >
              <SelectTrigger id='scoring-select' className='w-36'>
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
            <label htmlFor='rosterformat-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Roster Format
            </label>
            <Select
              value={config.roster_format}
              onValueChange={v => updateAndUnlock('roster_format', v as DraftConfig['roster_format'])}
            >
              <SelectTrigger id='rosterformat-select' className='w-56'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROSTER_FORMAT_OPTIONS.map(opt => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Season */}
          <div className='flex items-center justify-between gap-[var(--space-4)]'>
            <label htmlFor='season-select' className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
              Season
            </label>
            <Select
              value={String(config.season)}
              onValueChange={v => update('season', Number(v))}
            >
              <SelectTrigger id='season-select' className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='2026'>2026</SelectItem>
                <SelectItem value='2025'>2025</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Draft strategy dial -- only applied when a new session is created (Apply & New Draft below). */}
          <DraftStrategyToggle
            value={config.strategy}
            onChange={(s: DraftStrategy) => update('strategy', s)}
          />
        </div>

        <DialogFooter className='flex gap-[var(--space-2)] sm:flex-col'>
          <PressScale className='w-full'>
            <Button
              className='w-full'
              onClick={() => {
                onNewDraft()
                onOpenChange(false)
              }}
            >
              Apply &amp; New Draft
            </Button>
          </PressScale>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
