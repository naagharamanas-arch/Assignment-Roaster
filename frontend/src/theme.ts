import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

/**
 * Two-colour palette: midnight ink and champagne gold. No gradients anywhere.
 * Text uses the lightest ink tint so the UI stays strictly within those two hues.
 */
const ink = {
  50: '#E8EAF0',
  100: '#C9CEDB',
  200: '#A3ABBF',
  300: '#7C86A0',
  400: '#5A6582',
  500: '#3D4764',
  600: '#2A3350',
  700: '#1D2540',
  800: '#141B31',
  900: '#0E1325',
  950: '#0A0E1C',
}

const gold = {
  50: '#FBF6E6',
  100: '#F4E8BF',
  200: '#EBD78F',
  300: '#E0C468',
  400: '#D4AF4A',
  500: '#C9A03A',
  600: '#A8822B',
  700: '#856420',
  800: '#624A18',
  900: '#433212',
  950: '#2A1F0B',
}

type ScaleValue = { value: string }
const toTokens = (scale: Record<number, string>): Record<string, ScaleValue> =>
  Object.fromEntries(Object.entries(scale).map(([step, value]) => [step, { value }]))

const config = defineConfig({
  globalCss: {
    body: { bg: 'bg', color: 'fg' },
    '::selection': { bg: 'gold.500', color: 'ink.950' },
  },
  theme: {
    tokens: {
      colors: {
        ink: toTokens(ink),
        gold: toTokens(gold),
        // Any stray "gray" usage resolves to ink tints instead of a third hue.
        gray: toTokens(ink),
      },
    },
    semanticTokens: {
      colors: {
        bg: { DEFAULT: { value: '{colors.ink.950}' } },
        'bg.subtle': { value: '{colors.ink.900}' },
        'bg.muted': { value: '{colors.ink.800}' },
        'bg.panel': { value: '{colors.ink.900}' },
        'bg.emphasized': { value: '{colors.ink.700}' },
        fg: { DEFAULT: { value: '{colors.ink.50}' } },
        'fg.muted': { value: '{colors.ink.200}' },
        'fg.subtle': { value: '{colors.ink.300}' },
        'fg.inverted': { value: '{colors.ink.950}' },
        border: { DEFAULT: { value: '{colors.ink.700}' } },
        'border.muted': { value: '{colors.ink.800}' },
        'border.emphasized': { value: '{colors.ink.600}' },
        // colorPalette="gold"
        'gold.solid': { value: '{colors.gold.500}' },
        'gold.contrast': { value: '{colors.ink.950}' },
        'gold.fg': { value: '{colors.gold.300}' },
        'gold.muted': { value: '{colors.gold.900}' },
        'gold.subtle': { value: '{colors.gold.950}' },
        'gold.emphasized': { value: '{colors.gold.600}' },
        'gold.focusRing': { value: '{colors.gold.400}' },
        // colorPalette="gray" (neutral actions) stays in the ink family
        'gray.solid': { value: '{colors.ink.600}' },
        'gray.contrast': { value: '{colors.ink.50}' },
        'gray.fg': { value: '{colors.ink.100}' },
        'gray.muted': { value: '{colors.ink.800}' },
        'gray.subtle': { value: '{colors.ink.800}' },
        'gray.emphasized': { value: '{colors.ink.700}' },
        'gray.focusRing': { value: '{colors.gold.400}' },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
