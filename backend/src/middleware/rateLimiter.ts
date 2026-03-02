import rateLimit from 'express-rate-limit';

export const tutorLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 20,
  message: { error: 'Bạn gửi quá nhiều yêu cầu. Vui lòng thử lại sau.' }
});

export const aiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 5,
  message: { error: 'Bạn gửi quá nhiều yêu cầu AI. Vui lòng thử lại sau.' }
});
