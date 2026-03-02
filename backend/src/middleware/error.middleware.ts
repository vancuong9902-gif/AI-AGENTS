import { NextFunction, Request, Response } from 'express';
import { ApiError } from '../utils/ApiError.js';

export const errorHandler = (error: Error, _req: Request, res: Response, _next: NextFunction) => {
  if (error instanceof ApiError) {
    return res.status(error.statusCode).json({ error: error.message });
  }

  if (process.env.NODE_ENV === 'production') {
    return res.status(500).json({ error: 'Đã xảy ra lỗi hệ thống' });
  }

  return res.status(500).json({ error: error.message });
};
