import { InfoButton } from '@/components/ui/info-button';
import type { InfobarContent } from '@/components/ui/infobar';

type HeadingLevel = 1 | 2 | 3;

interface HeadingProps {
  title: string;
  description: string;
  infoContent?: InfobarContent;
  /**
   * Semantic heading level — controls both element (h1/h2/h3) and the
   * typography token pair (--fs-h{level} / --lh-h{level}) applied.
   * Defaults to 2 to preserve existing PageContainer page-title behavior.
   */
  level?: HeadingLevel;
}

const LEVEL_CLASSES: Record<HeadingLevel, string> = {
  1: 'text-[length:var(--fs-h1)] leading-[var(--lh-h1)]',
  2: 'text-[length:var(--fs-h2)] leading-[var(--lh-h2)]',
  3: 'text-[length:var(--fs-h3)] leading-[var(--lh-h3)]'
};

export function Heading({ title, description, infoContent, level = 2 }: HeadingProps) {
  const Tag = (`h${level}` as unknown) as 'h1' | 'h2' | 'h3';
  const sizeClass = LEVEL_CLASSES[level];

  return (
    <div className='space-y-[var(--space-1)]'>
      <div className='flex items-center gap-[var(--space-2)]'>
        <Tag className={`${sizeClass} font-bold tracking-tight`}>{title}</Tag>
        {infoContent && (
          <div className='pt-[var(--space-1)]'>
            <InfoButton content={infoContent} />
          </div>
        )}
      </div>
      {description && (
        <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          {description}
        </p>
      )}
    </div>
  );
}
