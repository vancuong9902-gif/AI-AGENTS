const { body, validationResult } = require('express-validator');

const emailRule = body('email').isEmail().withMessage('Invalid email format').normalizeEmail();
const passwordRule = body('password')
  .isLength({ min: 6 })
  .withMessage('Password must be at least 6 characters');
const nameRule = body('name').trim().notEmpty().withMessage('Name is required');

const handleValidation = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({ errors: errors.array() });
  }
  return next();
};

const registerValidator = [nameRule, emailRule, passwordRule, handleValidation];
const loginValidator = [emailRule, passwordRule, handleValidation];
const createTeacherValidator = [nameRule, emailRule, passwordRule, handleValidation];

module.exports = {
  registerValidator,
  loginValidator,
  createTeacherValidator
};
