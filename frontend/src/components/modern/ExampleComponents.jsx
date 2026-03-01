import { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Stack,
  Text,
  Tooltip,
  useDisclosure,
} from '@chakra-ui/react';

export default function ExampleComponents() {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [name, setName] = useState('');

  return (
    <Stack spacing='4'>
      <HStack spacing='3' wrap='wrap'>
        <Button>Primary action</Button>
        <Button variant='subtle'>Secondary action</Button>
        <Tooltip label='Creates a quick assignment draft'>
          <Button variant='outline'>Open tooltip action</Button>
        </Tooltip>
      </HStack>

      <Card>
        <CardHeader>
          <Text fontWeight='semibold'>Reusable card pattern</Text>
        </CardHeader>
        <CardBody>
          <Text color='mutedText'>Use this card style for progress, reminders, and classroom notices.</Text>
          <Button mt='4' onClick={onOpen}>
            Launch modal
          </Button>
        </CardBody>
      </Card>

      <Modal isOpen={isOpen} onClose={onClose} isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create announcement</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <FormControl>
              <FormLabel>Announcement title</FormLabel>
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder='Weekly quiz reminder' />
            </FormControl>
          </ModalBody>
          <ModalFooter>
            <HStack>
              <Button variant='ghost' onClick={onClose}>
                Cancel
              </Button>
              <Button onClick={onClose} isDisabled={!name.trim()}>
                Publish
              </Button>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Stack>
  );
}
