import { Router } from 'express';
import { createClass, listClasses, uploadDocument } from '../controllers/teacher.controller.js';
import { requireAuth, requireRole } from '../middleware/auth.middleware.js';
import { pdfUpload, validatePdfMagic } from '../middleware/upload.middleware.js';
import { asyncHandler } from '../utils/asyncHandler.js';

const router = Router();
router.use(requireAuth, requireRole('TEACHER'));

router.post('/classes', asyncHandler(createClass));
router.get('/classes', asyncHandler(listClasses));
router.post('/classes/:classId/documents', pdfUpload.single('file'), asyncHandler(async (req, _res, next) => {
  if (req.file) await validatePdfMagic(req.file.path);
  next();
}), asyncHandler(uploadDocument));

export default router;
