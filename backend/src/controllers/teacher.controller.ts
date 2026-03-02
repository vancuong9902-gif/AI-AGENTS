import { Response } from 'express';
import { nanoid } from 'nanoid';
import { AuthRequest } from '../middleware/auth.middleware.js';
import { prisma } from '../utils/prisma.js';
import { ApiError } from '../utils/ApiError.js';

export const createClass = async (req: AuthRequest, res: Response) => {
  const { name, subject, description, maxStudents } = req.body;
  const newClass = await prisma.class.create({
    data: {
      name,
      subject,
      description,
      maxStudents: maxStudents ?? 50,
      inviteCode: nanoid(6).toUpperCase(),
      teacherId: req.user!.userId
    }
  });
  res.status(201).json(newClass);
};

export const listClasses = async (req: AuthRequest, res: Response) => {
  const classes = await prisma.class.findMany({
    where: { teacherId: req.user!.userId },
    include: { _count: { select: { enrollments: true } } },
    orderBy: { createdAt: 'desc' }
  });
  res.json(classes);
};

export const uploadDocument = async (req: AuthRequest, res: Response) => {
  if (!req.file) throw new ApiError(400, 'Thiếu tệp PDF');
  const classId = req.params.classId;
  const created = await prisma.document.create({
    data: {
      classId,
      filename: req.file.originalname,
      filepath: req.file.path,
      fileSize: req.file.size,
      status: 'PROCESSING'
    }
  });

  res.status(201).json({ message: 'Đã tải lên tài liệu, hệ thống đang xử lý AI', document: created });
};
