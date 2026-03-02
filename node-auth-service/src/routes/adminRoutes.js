const express = require('express');
const authMiddleware = require('../middleware/authMiddleware');
const roleMiddleware = require('../middleware/roleMiddleware');
const { createTeacher } = require('../controllers/adminController');
const { createTeacherValidator } = require('../validators/authValidators');

const router = express.Router();

router.post('/create-teacher', authMiddleware, roleMiddleware('admin'), createTeacherValidator, createTeacher);

module.exports = router;
