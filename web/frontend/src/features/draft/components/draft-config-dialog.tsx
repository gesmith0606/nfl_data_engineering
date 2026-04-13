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
import { Button } from '@/components/ui/button'
import type { DraftConfig } from '@/lib/nfl/types'

interface DraftConfigDialogProps {
  config: DraftConfig
  onConfigChange: (config: DraftConfig) => void
  onStartMock: () => void
  open: boolean
  onOpenChange: (open: boolean) => void
  onNewDraft: () => void
}

export function DraftConfigDialog({
  config,
  onConfigChange,
  onStartMock,
  open,
  onOpenChange,
  onNewDraft
}: DraftConfigDialogProps) {
  function update<K extends keyof DraftConfig>(key: K, value: DraftConfig[K]) {
    onConfigChange({ ...config, [key]: value })
  }

  const teamCounts = [8, 10, 12, 14]
  const picks = Array.from({ length: config.n_teams }, (_, i) => i + 1)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Draft Settings</DialogTitle>
        </DialogHeader>

        <div className='space-y-4 py-2'>
          {/* Teams */}
          <div className='flex items-center justify-between gap-4'>
            <label className='text-sm font-medium'>Teams</label>
            <Select
              value={String(config.n_teams)}
              onValueChange={v => {
                const n = Number(v)
                update('n_teams', n)
                if (config.user_pick > n) update('user_pick', n)
              }}
            >
              <SelectTrigger className='w-32'>
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
          <div className='flex items-center justify-between gap-4'>
            <label className='text-sm font-medium'>My Pick</label>
            <Select
              value={String(config.user_pick)}
              onValueChange={v => update('user_pick', Number(v))}
            >
              <SelectTrigger className='w-32'>
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
          <div className='flex items-center justify-between gap-4'>
            <label className='text-sm font-medium'>Scoring</label>
            <Select
              value={config.scoring}
              onValueChange={v => update('scoring', v as DraftConfig['scoring'])}
            >
              <SelectTrigger className='w-32'>
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
          <div className='flex items-center justify-between gap-4'>
            <label className='text-sm font-medium'>Roster Format</label>
            <Select
              value={config.roster_format}
              onValueChange={v => update('roster_format', v as DraftConfig['roster_format'])}
            >
              <SelectTrigger className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='standard'>Standard</SelectItem>
                <SelectItem value='superflex'>Superflex</SelectItem>
                <SelectItem value='2qb'>2QB</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Season */}
          <div className='flex items-center justify-between gap-4'>
            <label className='text-sm font-medium'>Season</label>
            <Select
              value={String(config.season)}
              onValueChange={v => update('season', Number(v))}
            >
              <SelectTrigger className='w-32'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='2026'>2026</SelectItem>
                <SelectItem value='2025'>2025</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter className='flex gap-2 sm:flex-col'>
          <Button
            className='w-full'
            onClick={() => {
              onNewDraft()
              onOpenChange(false)
            }}
          >
            Apply &amp; New Draft
          </Button>
          <Button
            variant='outline'
            className='w-full'
            onClick={() => {
              onStartMock()
              onOpenChange(false)
            }}
          >
            Start Mock Draft
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
