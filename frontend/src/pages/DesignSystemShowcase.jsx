import { Box, Container, Divider, Heading, Stack, Text } from '@chakra-ui/react';
import ResponsiveNavbar from '../components/modern/ResponsiveNavbar';
import DashboardLayout from '../components/modern/DashboardLayout';
import ExampleComponents from '../components/modern/ExampleComponents';

export default function DesignSystemShowcase() {
  return (
    <Box>
      <ResponsiveNavbar />
      <Container maxW='7xl' py='8'>
        <Stack spacing='10'>
          <Box id='courses'>
            <Heading size='lg' mb='2'>
              Modern Chakra UI Learning Experience
            </Heading>
            <Text color='mutedText'>
              Accessible, responsive, and reusable UI patterns for students and teachers.
            </Text>
          </Box>

          <DashboardLayout role='student' />
          <Divider />
          <DashboardLayout role='teacher' />
          <Divider />

          <Box id='assessments'>
            <Heading size='md' mb='4'>
              Button, Card, Modal, Tooltip Patterns
            </Heading>
            <ExampleComponents />
          </Box>
        </Stack>
      </Container>
    </Box>
  );
}
