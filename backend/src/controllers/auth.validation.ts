import { ApiError } from '../utils/ApiError.js';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type RegisterPayload = {
  name: string;
  email: string;
  password: string;
  role: 'TEACHER' | 'STUDENT';
};

export const normalizeRegisterPayload = (body: unknown): RegisterPayload => {
  const raw = (body ?? {}) as Record<string, unknown>;
  const name = String(raw.name ?? '').trim();
  const email = String(raw.email ?? '').trim().toLowerCase();
  const password = String(raw.password ?? '').trim();
  const roleInput = String(raw.role ?? 'student').trim().toLowerCase();

  if (!name) throw new ApiError(400, 'Tên không được để trống');
  if (!email || !EMAIL_REGEX.test(email)) {
    throw new ApiError(400, 'Email không hợp lệ');
  }
  if (!password || password.length < 8) {
    throw new ApiError(400, 'Mật khẩu phải có ít nhất 8 ký tự');
  }

  const roleMap: Record<string, RegisterPayload['role']> = {
    teacher: 'TEACHER',
    student: 'STUDENT',
  };
  const role = roleMap[roleInput];
  if (!role) {
    throw new ApiError(400, 'Vai trò không hợp lệ');
  }

  return { name, email, password, role };
};
