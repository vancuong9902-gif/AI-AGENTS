import { NextFunction, Request, Response } from 'express';
import { Role } from '@prisma/client';
import { verifyToken } from '../utils/jwt.js';
import { ApiError } from '../utils/ApiError.js';

export interface AuthRequest extends Request {
  user?: {
    userId: string;
    role: Role;
    name: string;
    email: string;
  };
}

export const requireAuth = (req: AuthRequest, _res: Response, next: NextFunction) => {
  const authHeader = req.headers.authorization;
  if (!authHeader?.startsWith('Bearer ')) {
    return next(new ApiError(401, 'Thiếu token xác thực'));
  }

  try {
    req.user = verifyToken(authHeader.replace('Bearer ', '')) as AuthRequest['user'];
    return next();
  } catch {
    return next(new ApiError(401, 'Token không hợp lệ hoặc đã hết hạn'));
  }
};

export const requireRole = (role: Role) => (req: AuthRequest, _res: Response, next: NextFunction) => {
  if (req.user?.role !== role) {
    return next(new ApiError(403, 'Bạn không có quyền truy cập'));
  }
  return next();
};
