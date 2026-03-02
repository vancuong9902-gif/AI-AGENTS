import { Response } from 'express';
import { AuthRequest } from '../middleware/auth.middleware.js';
import { prisma } from '../utils/prisma.js';
import { ApiError } from '../utils/ApiError.js';

export const joinClass = async (req: AuthRequest, res: Response) => {
  const { inviteCode } = req.body;
  const foundClass = await prisma.class.findUnique({ where: { inviteCode } });
  if (!foundClass) throw new ApiError(404, 'Không tìm thấy lớp học');

  const enrollment = await prisma.enrollment.upsert({
    where: { studentId_classId: { studentId: req.user!.userId, classId: foundClass.id } },
    update: {},
    create: { studentId: req.user!.userId, classId: foundClass.id }
  });

  res.json({ message: 'Tham gia lớp học thành công', enrollment });
};

export const myClasses = async (req: AuthRequest, res: Response) => {
  const classes = await prisma.enrollment.findMany({
    where: { studentId: req.user!.userId },
    include: { class: { include: { teacher: { select: { name: true } } } } }
  });
  res.json(classes);
};
