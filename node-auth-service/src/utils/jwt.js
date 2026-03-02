const jwt = require('jsonwebtoken');

const signToken = ({ id, role }) => {
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    throw new Error('JWT_SECRET is required');
  }

  return jwt.sign({ id, role }, secret, { expiresIn: '1d' });
};

module.exports = { signToken };
