import { extendTheme } from '@chakra-ui/react';

const colors = {
  brand: {
    50: '#eef6ff',
    100: '#d9eaff',
    200: '#b8d7ff',
    300: '#89bcff',
    400: '#579dff',
    500: '#2f7cf5',
    600: '#1f62d8',
    700: '#194eaf',
    800: '#1a438d',
    900: '#1c3a74',
  },
  accent: {
    50: '#ecfbf5',
    100: '#cff4e5',
    200: '#a7e7cf',
    300: '#74d8b4',
    400: '#45c899',
    500: '#26af7f',
    600: '#188d67',
    700: '#136f52',
    800: '#135943',
    900: '#124937',
  },
};

const fonts = {
  heading: `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`,
  body: `Source Serif 4, Georgia, Cambria, 'Times New Roman', serif`,
};

const semanticTokens = {
  colors: {
    appBg: { default: 'gray.50', _dark: 'gray.900' },
    surface: { default: 'white', _dark: 'gray.800' },
    borderSubtle: { default: 'gray.200', _dark: 'whiteAlpha.300' },
    bodyText: { default: 'gray.700', _dark: 'gray.100' },
    mutedText: { default: 'gray.500', _dark: 'gray.300' },
    cardShadow: { default: 'rgba(15, 23, 42, 0.08)', _dark: 'rgba(0, 0, 0, 0.35)' },
  },
};

const components = {
  Button: {
    baseStyle: {
      borderRadius: 'xl',
      fontWeight: '600',
      _focusVisible: {
        boxShadow: '0 0 0 3px var(--chakra-colors-brand-200)',
      },
    },
    variants: {
      solid: {
        bg: 'brand.500',
        color: 'white',
        _hover: { bg: 'brand.600' },
      },
      subtle: {
        bg: 'brand.50',
        color: 'brand.700',
        _hover: { bg: 'brand.100' },
      },
    },
    defaultProps: {
      colorScheme: 'brand',
      size: 'md',
    },
  },
  Card: {
    baseStyle: {
      container: {
        borderRadius: '2xl',
        borderWidth: '1px',
        borderColor: 'borderSubtle',
        bg: 'surface',
        boxShadow: '0 10px 30px var(--chakra-colors-cardShadow)',
      },
    },
  },
  Input: {
    variants: {
      outline: {
        field: {
          borderRadius: 'xl',
          borderColor: 'borderSubtle',
          _focusVisible: {
            borderColor: 'brand.500',
            boxShadow: '0 0 0 1px var(--chakra-colors-brand-500)',
          },
        },
      },
    },
  },
  Modal: {
    baseStyle: {
      dialog: {
        borderRadius: '2xl',
      },
    },
  },
  Tooltip: {
    baseStyle: {
      borderRadius: 'md',
      fontSize: 'xs',
    },
  },
};

const theme = extendTheme({
  colors,
  fonts,
  semanticTokens,
  breakpoints: {
    sm: '30em',
    md: '48em',
    lg: '62em',
    xl: '80em',
    '2xl': '96em',
  },
  radii: {
    xl: '0.9rem',
    '2xl': '1.25rem',
  },
  lineHeights: {
    base: 1.7,
    tall: 1.85,
  },
  textStyles: {
    h1: { fontSize: ['2xl', '3xl', '4xl'], lineHeight: 1.2, fontWeight: 700, letterSpacing: '-0.02em' },
    h2: { fontSize: ['xl', '2xl'], lineHeight: 1.25, fontWeight: 700 },
    body: { fontSize: ['sm', 'md'], lineHeight: 'tall' },
    caption: { fontSize: 'xs', lineHeight: 1.4, color: 'mutedText' },
  },
  styles: {
    global: {
      body: {
        bg: 'appBg',
        color: 'bodyText',
      },
      '*:focus-visible': {
        outline: '2px solid',
        outlineColor: 'brand.400',
        outlineOffset: '2px',
      },
    },
  },
  components,
  config: {
    initialColorMode: 'light',
    useSystemColorMode: true,
  },
});

export default theme;
