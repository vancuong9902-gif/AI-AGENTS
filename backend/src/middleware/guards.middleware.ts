import { NextFunction, Response } from 'express';
import { AuthRequest } from './auth.middleware.js';
import { prisma } from '../utils/prisma.js';
import { ApiError } from '../utils/ApiError.js';

export const hasReadyDocument = async (req: AuthRequest, _res: Response, next: NextFunction) => {
  const classId = req.params.classId ?? req.body.classId;
  if (!classId) {
    return next(new ApiError(400, 'Thiếu mã lớp học'));
  }

  const doc = await prisma.document.findFirst({ where: { classId, status: 'READY' } });
  if (!doc) {
    return next(new ApiError(403, 'Giáo viên chưa tải tài liệu'));
  }

  return next();
};
