import { Router } from 'express';
import { joinClass, myClasses } from '../controllers/student.controller.js';
import { requireAuth, requireRole } from '../middleware/auth.middleware.js';
import { asyncHandler } from '../utils/asyncHandler.js';

const router = Router();
router.use(requireAuth, requireRole('STUDENT'));

router.post('/join-class', asyncHandler(joinClass));
router.get('/classes', asyncHandler(myClasses));

export default router;
