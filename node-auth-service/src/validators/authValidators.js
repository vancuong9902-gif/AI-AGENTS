const { body, validationResult } = require('express-validator');

const emailRule = body('email').isEmail().withMessage('Invalid email format').normalizeEmail();
const passwordRule = body('password')
  .isLength({ min: 6 })
  .withMessage('Password must be at least 6 characters');
const fullNameRule = body('fullName').trim().notEmpty().withMessage('Full name is required');

const disallowExtraFields = (allowedFields) => (req, res, next) => {
  const extraFields = Object.keys(req.body || {}).filter((field) => !allowedFields.includes(field));
  if (extraFields.length > 0) {
    return res.status(400).json({
      message: `Unexpected field(s): ${extraFields.join(', ')}`
    });
  }
  return next();
};

const handleValidation = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({ errors: errors.array() });
  }
  return next();
};

const registerValidator = [
  disallowExtraFields(['email', 'password', 'fullName']),
  fullNameRule,
  emailRule,
  passwordRule,
  handleValidation
];
const roleRule = body('role').optional().isIn(['admin', 'teacher', 'student']).withMessage('Invalid role');

const loginValidator = [
  disallowExtraFields(['email', 'password', 'role']),
  emailRule,
  passwordRule,
  roleRule,
  handleValidation
];
const createTeacherValidator = [
  disallowExtraFields(['email', 'password', 'name']),
  body('name').trim().notEmpty().withMessage('Name is required'),
  emailRule,
  passwordRule,
  handleValidation
];

module.exports = {
  registerValidator,
  loginValidator,
  createTeacherValidator
};
