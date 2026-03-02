import { Request, Response } from 'express';
import bcrypt from 'bcrypt';
import { prisma } from '../utils/prisma.js';
import { ApiError } from '../utils/ApiError.js';
import { signToken } from '../utils/jwt.js';

export const register = async (req: Request, res: Response) => {
  const { name, email, password, role } = req.body;
  if (!name || !email || !password || password.length < 8) {
    throw new ApiError(400, 'Thông tin đăng ký không hợp lệ');
  }
  const existed = await prisma.user.findUnique({ where: { email } });
  if (existed) throw new ApiError(409, 'Email đã tồn tại');

  const user = await prisma.user.create({
    data: { name, email, password: await bcrypt.hash(password, 10), role }
  });

  const token = signToken({ userId: user.id, role: user.role, name: user.name, email: user.email });
  res.status(201).json({ token, user: { id: user.id, name, email, role: user.role } });
};

export const login = async (req: Request, res: Response) => {
  const { email, password } = req.body;
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user || !(await bcrypt.compare(password, user.password))) {
    throw new ApiError(401, 'Email hoặc mật khẩu không đúng');
  }

  const token = signToken({ userId: user.id, role: user.role, name: user.name, email: user.email });
  res.json({ token, user: { id: user.id, name: user.name, email, role: user.role } });
};

export const me = async (req: Request & { user?: { userId: string } }, res: Response) => {
  const user = await prisma.user.findUnique({
    where: { id: req.user?.userId },
    select: { id: true, name: true, email: true, role: true }
  });
  res.json(user);
};
