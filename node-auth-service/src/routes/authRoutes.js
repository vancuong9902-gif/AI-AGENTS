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

router.post('/register', registerValidator, register);

router.post('/login', loginLimiter, loginValidator, login);

module.exports = router;
