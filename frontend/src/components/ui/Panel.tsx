import { Box, type BoxProps } from '@chakra-ui/react'
import { motion } from 'framer-motion'

/** Solid ink surface with a hairline border. */
export function Panel({ children, ...rest }: BoxProps) {
  return (
    <Box
      asChild
      {...rest}
      p="6"
      rounded="lg"
      bg="bg.panel"
      borderWidth="1px"
      borderColor="border"
      _hover={{ borderColor: 'gold.700' }}
    >
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        {children}
      </motion.div>
    </Box>
  )
}
