import { Button, HStack, Text, Stack } from '@chakra-ui/react'
import type { LanguageStyle, RoastLevel } from '../../types'

export const ROAST_LEVELS: { value: RoastLevel; label: string }[] = [
  { value: 'mild', label: 'Mild' },
  { value: 'medium', label: 'Medium' },
  { value: 'savage', label: 'Savage' },
]

export const LANGUAGE_STYLES: { value: LanguageStyle; label: string }[] = [
  { value: 'tamil_script', label: 'தமிழ் (Tamil script)' },
  { value: 'tanglish', label: 'Tanglish' },
]

interface OptionGroupProps<T extends string> {
  legend: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}

export function OptionGroup<T extends string>({ legend, options, value, onChange }: OptionGroupProps<T>) {
  return (
    <Stack gap="2" role="radiogroup" aria-label={legend}>
      <Text fontWeight="semibold" fontSize="sm">{legend}</Text>
      <HStack wrap="wrap" gap="2">
        {options.map((o) => (
          <Button
            key={o.value}
            size="sm"
            rounded="full"
            role="radio"
            aria-checked={o.value === value}
            variant={o.value === value ? 'solid' : 'outline'}
            colorPalette="gold"
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </Button>
        ))}
      </HStack>
    </Stack>
  )
}
