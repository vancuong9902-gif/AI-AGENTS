import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET ?? 'development-secret-key-minimum-32-chars';
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN ?? '7d';

export const signToken = (payload: Record<string, unknown>) =>
  jwt.sign(payload, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN });

export const verifyToken = (token: string) => jwt.verify(token, JWT_SECRET);
