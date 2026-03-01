import {
  Box,
  Card,
  CardBody,
  CardHeader,
  Flex,
  Grid,
  GridItem,
  Heading,
  HStack,
  Icon,
  Progress,
  Stack,
  Stat,
  StatHelpText,
  StatLabel,
  StatNumber,
  Text,
} from '@chakra-ui/react';
import { FiAward, FiBookOpen, FiClock, FiUsers } from 'react-icons/fi';
import AITutorChat from './AITutorChat';

const studentStats = [
  { label: 'Weekly Study Time', value: '6.4h', hint: '+18% from last week', icon: FiClock },
  { label: 'Completed Lessons', value: '12', hint: '3 pending this week', icon: FiBookOpen },
  { label: 'Current Streak', value: '9 days', hint: 'Keep momentum', icon: FiAward },
];

const teacherStats = [
  { label: 'Active Students', value: '148', hint: 'Across 5 classrooms', icon: FiUsers },
  { label: 'Assignments to Review', value: '23', hint: '12 due today', icon: FiBookOpen },
  { label: 'Class Completion', value: '76%', hint: '+5% this month', icon: FiAward },
];

function StatCards({ items }) {
  return (
    <Grid templateColumns={{ base: '1fr', md: 'repeat(3, minmax(0, 1fr))' }} gap='4'>
      {items.map((item) => (
        <Card key={item.label}>
          <CardBody>
            <HStack justify='space-between' align='start'>
              <Stat>
                <StatLabel>{item.label}</StatLabel>
                <StatNumber>{item.value}</StatNumber>
                <StatHelpText>{item.hint}</StatHelpText>
              </Stat>
              <Flex bg='brand.50' color='brand.600' p='2.5' borderRadius='lg'>
                <Icon as={item.icon} />
              </Flex>
            </HStack>
          </CardBody>
        </Card>
      ))}
    </Grid>
  );
}

export default function DashboardLayout({ role = 'student' }) {
  const isTeacher = role === 'teacher';

  return (
    <Grid templateColumns={{ base: '1fr', xl: '2fr 1fr' }} gap='6' alignItems='start'>
      <GridItem>
        <Stack spacing='6'>
          <Box>
            <Heading textStyle='h1'>{isTeacher ? 'Teacher Dashboard' : 'Student Dashboard'}</Heading>
            <Text color='mutedText' mt='2'>
              {isTeacher
                ? 'Track class health, upcoming grading workload, and student engagement in one view.'
                : 'Focus on your next actions, learning goals, and milestones with a calm, distraction-free layout.'}
            </Text>
          </Box>

          <StatCards items={isTeacher ? teacherStats : studentStats} />

          <Card>
            <CardHeader>
              <Heading size='md'>Learning Path Progress</Heading>
            </CardHeader>
            <CardBody>
              <Stack spacing='4'>
                {[
                  { title: 'Foundations', value: 92 },
                  { title: 'Applied Practice', value: 67 },
                  { title: 'Final Assessment Prep', value: 43 },
                ].map((item) => (
                  <Box key={item.title}>
                    <Flex justify='space-between' mb='1.5'>
                      <Text fontWeight='medium'>{item.title}</Text>
                      <Text fontSize='sm' color='mutedText'>
                        {item.value}%
                      </Text>
                    </Flex>
                    <Progress value={item.value} borderRadius='full' colorScheme='green' />
                  </Box>
                ))}
              </Stack>
            </CardBody>
          </Card>
        </Stack>
      </GridItem>

      <GridItem id='ai-tutor' minH='560px'>
        <AITutorChat />
      </GridItem>
    </Grid>
  );
}
