import {
  Box,
  Button,
  Flex,
  HStack,
  Icon,
  IconButton,
  Link,
  Stack,
  Text,
  useColorMode,
  useDisclosure,
} from '@chakra-ui/react';
import { FiBarChart2, FiBookOpen, FiMenu, FiMoon, FiSun, FiUser } from 'react-icons/fi';

const navItems = [
  { label: 'Courses', href: '#courses', icon: FiBookOpen },
  { label: 'Assessments', href: '#assessments', icon: FiBarChart2 },
  { label: 'AI Tutor', href: '#ai-tutor', icon: FiUser },
];

export default function ResponsiveNavbar() {
  const { isOpen, onToggle } = useDisclosure();
  const { colorMode, toggleColorMode } = useColorMode();

  return (
    <Box as='nav' bg='surface' borderBottomWidth='1px' borderColor='borderSubtle' position='sticky' top='0' zIndex='sticky'>
      <Flex maxW='7xl' mx='auto' align='center' justify='space-between' py='3' px={{ base: 4, md: 6 }}>
        <Text textStyle='h2'>EduAI Studio</Text>

        <HStack spacing='3' display={{ base: 'none', md: 'flex' }}>
          {navItems.map((item) => (
            <Button as={Link} key={item.label} href={item.href} variant='ghost' leftIcon={<Icon as={item.icon} />}>
              {item.label}
            </Button>
          ))}
          <IconButton
            aria-label={colorMode === 'light' ? 'Enable dark mode' : 'Enable light mode'}
            icon={colorMode === 'light' ? <FiMoon /> : <FiSun />}
            onClick={toggleColorMode}
            variant='subtle'
          />
          <Button>Sign in</Button>
        </HStack>

        <HStack display={{ base: 'flex', md: 'none' }}>
          <IconButton
            aria-label={colorMode === 'light' ? 'Enable dark mode' : 'Enable light mode'}
            icon={colorMode === 'light' ? <FiMoon /> : <FiSun />}
            onClick={toggleColorMode}
            variant='ghost'
          />
          <IconButton aria-label='Open navigation menu' icon={<FiMenu />} onClick={onToggle} />
        </HStack>
      </Flex>

      {isOpen ? (
        <Stack pb='4' px='4' spacing='2' display={{ md: 'none' }}>
          {navItems.map((item) => (
            <Button as={Link} key={item.label} href={item.href} justifyContent='flex-start' variant='ghost' leftIcon={<Icon as={item.icon} />}>
              {item.label}
            </Button>
          ))}
          <Button>Sign in</Button>
        </Stack>
      ) : null}
    </Box>
  );
}
