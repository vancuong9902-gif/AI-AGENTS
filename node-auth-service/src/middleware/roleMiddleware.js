const roleMiddleware = (requiredRole) => (req, res, next) => {
  if (!req.user || req.user.role !== requiredRole) {
    return res.status(403).json({ message: 'Forbidden' });
  }
  return next();
};

module.exports = roleMiddleware;
