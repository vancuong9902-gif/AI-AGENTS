const express = require('express');
const rateLimit = require('express-rate-limit');
const { register, login } = require('../controllers/authController');
const { registerValidator, loginValidator } = require('../validators/authValidators');

const router = express.Router();

const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { message: 'Too many login attempts, please try again later' }
});

router.post('/register', registerValidator, (req, res, next) => {
  if (Object.prototype.hasOwnProperty.call(req.body, 'role')) {
    return res.status(400).json({ message: 'Role cannot be set via register' });
  }
  return register(req, res, next);
});

router.post('/login', loginLimiter, loginValidator, login);

module.exports = router;
