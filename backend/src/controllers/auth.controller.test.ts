import { describe, expect, it } from 'vitest';

import { ApiError } from '../utils/ApiError.js';
import { normalizeRegisterPayload } from './auth.validation.js';

describe('normalizeRegisterPayload', () => {
  it('normalizes email and maps lowercase role to prisma enum', () => {
    const payload = normalizeRegisterPayload({
      name: '  Nguyen Van A ',
      email: '  User@Example.com ',
      password: '12345678',
      role: 'teacher',
    });

    expect(payload).toEqual({
      name: 'Nguyen Van A',
      email: 'user@example.com',
      password: '12345678',
      role: 'TEACHER',
    });
  });

  it('uses STUDENT as default role when missing', () => {
    const payload = normalizeRegisterPayload({
      name: 'Student',
      email: 'student@example.com',
      password: '12345678',
    });

    expect(payload.role).toBe('STUDENT');
  });

  it('throws 400 for invalid role', () => {
    expect(() =>
      normalizeRegisterPayload({
        name: 'Student',
        email: 'student@example.com',
        password: '12345678',
        role: 'admin',
      }),
    ).toThrowError(ApiError);
  });
});
