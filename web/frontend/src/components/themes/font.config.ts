import localFont from 'next/font/local';

import { cn } from '@/lib/utils';

/**
 * Self-hosted fonts (latin subset woff2 from Google Fonts, SIL OFL 1.1 — licence
 * texts in src/fonts/licenses/). Replaces next/font/google, whose build-time
 * fetch from fonts.googleapis.com made Vercel builds flaky. CSS variable names
 * are unchanged.
 */

const fontSans = localFont({
  src: '../../fonts/Geist.woff2',
  weight: '100 900',
  display: 'swap',
  variable: '--font-sans'
});

const fontMono = localFont({
  src: '../../fonts/GeistMono.woff2',
  weight: '100 900',
  display: 'swap',
  variable: '--font-mono'
});

const fontInstrument = localFont({
  src: '../../fonts/InstrumentSans.woff2',
  weight: '400 700',
  display: 'swap',
  variable: '--font-instrument'
});

const fontNotoMono = localFont({
  src: '../../fonts/NotoSansMono.woff2',
  weight: '100 900',
  display: 'swap',
  variable: '--font-noto-mono'
});

const fontMullish = localFont({
  src: '../../fonts/Mulish.woff2',
  weight: '200 1000',
  display: 'swap',
  variable: '--font-mullish'
});

const fontInter = localFont({
  src: '../../fonts/Inter.woff2',
  weight: '100 900',
  display: 'swap',
  variable: '--font-inter'
});

const fontArchitectsDaughter = localFont({
  src: '../../fonts/ArchitectsDaughter-400.woff2',
  weight: '400',
  display: 'swap',
  variable: '--font-architects-daughter'
});

const fontDMSans = localFont({
  src: '../../fonts/DMSans.woff2',
  weight: '100 1000',
  display: 'swap',
  variable: '--font-dm-sans'
});

const fontFiraCode = localFont({
  src: '../../fonts/FiraCode.woff2',
  weight: '300 700',
  display: 'swap',
  variable: '--font-fira-code'
});

const fontOutfit = localFont({
  src: '../../fonts/Outfit.woff2',
  weight: '100 900',
  display: 'swap',
  variable: '--font-outfit'
});

const fontSpaceMono = localFont({
  src: [
    { path: '../../fonts/SpaceMono-400.woff2', weight: '400' },
    { path: '../../fonts/SpaceMono-700.woff2', weight: '700' }
  ],
  display: 'swap',
  variable: '--font-space-mono'
});

const fontJetBrainsMono = localFont({
  src: '../../fonts/JetBrainsMono.woff2',
  weight: '100 800',
  display: 'swap',
  variable: '--font-jetbrains-mono'
});

const fontMerriweather = localFont({
  src: '../../fonts/Merriweather.woff2',
  weight: '300 900',
  display: 'swap',
  variable: '--font-merriweather'
});

const fontPlayfairDisplay = localFont({
  src: '../../fonts/PlayfairDisplay.woff2',
  weight: '400 900',
  display: 'swap',
  variable: '--font-playfair-display'
});

const fontArchivo = localFont({
  src: '../../fonts/Archivo.woff2',
  weight: '400 700',
  display: 'swap',
  variable: '--font-archivo'
});

const fontBarlowCondensed = localFont({
  src: [
    { path: '../../fonts/BarlowCondensed-600.woff2', weight: '600' },
    { path: '../../fonts/BarlowCondensed-700.woff2', weight: '700' },
    { path: '../../fonts/BarlowCondensed-800.woff2', weight: '800' }
  ],
  display: 'swap',
  variable: '--font-barlow-condensed'
});

export const fontVariables = cn(
  fontSans.variable,
  fontMono.variable,
  fontInstrument.variable,
  fontNotoMono.variable,
  fontMullish.variable,
  fontInter.variable,
  fontArchitectsDaughter.variable,
  fontDMSans.variable,
  fontFiraCode.variable,
  fontOutfit.variable,
  fontSpaceMono.variable,
  fontJetBrainsMono.variable,
  fontMerriweather.variable,
  fontPlayfairDisplay.variable,
  fontArchivo.variable,
  fontBarlowCondensed.variable
);
