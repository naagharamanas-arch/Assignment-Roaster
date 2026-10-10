import { Box, chakra } from '@chakra-ui/react'
import { motion } from 'framer-motion'
import type { ButtonHTMLAttributes } from 'react'

const StyledButton = chakra('button')

/** Solid gold call-to-action button. */
export function PrimaryButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <Box asChild display="inline-block">
      <motion.div whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }}>
        <StyledButton
          px="6"
          py="3"
          rounded="md"
          fontWeight="semibold"
          letterSpacing="0.02em"
          color="ink.950"
          bg="gold.500"
          cursor="pointer"
          _hover={{ bg: 'gold.400' }}
          _focusVisible={{ outline: '2px solid', outlineColor: 'gold.300', outlineOffset: '2px' }}
          _disabled={{ opacity: 0.6, cursor: 'not-allowed' }}
          {...props}
        >
          {children}
        </StyledButton>
      </motion.div>
    </Box>
  )
}
