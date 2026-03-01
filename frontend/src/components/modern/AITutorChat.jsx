import { useMemo, useState } from 'react';
import {
  Avatar,
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Input,
  Stack,
  Text,
} from '@chakra-ui/react';

const initialMessages = [
  {
    id: 1,
    role: 'assistant',
    content: 'Hi! I reviewed your progress. Want a 15-minute algebra recap plan?',
    time: '09:12',
  },
  {
    id: 2,
    role: 'user',
    content: 'Yes, and include 2 quick practice questions.',
    time: '09:13',
  },
  {
    id: 3,
    role: 'assistant',
    content: 'Great! I prepared a short plan with spaced practice and instant feedback.',
    time: '09:14',
  },
];

export default function AITutorChat() {
  const [messages, setMessages] = useState(initialMessages);
  const [value, setValue] = useState('');

  const typing = useMemo(() => messages[messages.length - 1]?.role === 'user', [messages]);

  const onSend = () => {
    if (!value.trim()) return;
    const nextUserMessage = {
      id: Date.now(),
      role: 'user',
      content: value,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [
      ...prev,
      nextUserMessage,
      {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Noted. I added this request to your adaptive learning plan and generated follow-up prompts.',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
    setValue('');
  };

  return (
    <Box borderWidth='1px' borderColor='borderSubtle' bg='surface' borderRadius='2xl' h='full' display='flex' flexDirection='column'>
      <Flex p='4' borderBottomWidth='1px' borderColor='borderSubtle' justify='space-between' align='center'>
        <HStack>
          <Avatar name='AI Tutor' size='sm' bg='brand.500' color='white' />
          <Box>
            <Text fontWeight='semibold'>AI Tutor</Text>
            <Text fontSize='sm' color='mutedText'>Adaptive support for every lesson</Text>
          </Box>
        </HStack>
        <Badge colorScheme='green'>Online</Badge>
      </Flex>

      <Stack spacing='3' p='4' flex='1' overflowY='auto'>
        {messages.map((message) => (
          <Flex key={message.id} justify={message.role === 'user' ? 'flex-end' : 'flex-start'}>
            <Box
              maxW='80%'
              px='4'
              py='3'
              borderRadius='2xl'
              bg={message.role === 'user' ? 'brand.500' : 'gray.100'}
              color={message.role === 'user' ? 'white' : 'bodyText'}
            >
              <Text textStyle='body'>{message.content}</Text>
              <Text fontSize='xs' mt='1' opacity='0.7'>
                {message.time}
              </Text>
            </Box>
          </Flex>
        ))}

        {typing ? (
          <HStack color='mutedText' fontSize='sm'>
            <Text>AI is typing</Text>
            <Box as='span' animation='pulse 1.2s ease-in-out infinite'>•••</Box>
          </HStack>
        ) : null}
      </Stack>

      <HStack p='4' borderTopWidth='1px' borderColor='borderSubtle'>
        <Input
          placeholder='Ask your AI tutor…'
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onSend();
          }}
        />
        <Button onClick={onSend}>Send</Button>
      </HStack>
    </Box>
  );
}
