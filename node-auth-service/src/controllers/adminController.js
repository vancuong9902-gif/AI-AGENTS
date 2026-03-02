const bcrypt = require('bcrypt');
const pool = require('../config/db');
const { SALT_ROUNDS } = require('./authController');

const createTeacher = async (req, res) => {
  const { name, email, password } = req.body;

  try {
    const [existing] = await pool.execute('SELECT id FROM users WHERE email = ?', [email]);
    if (existing.length > 0) {
      return res.status(409).json({ message: 'Email already exists' });
    }

    const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);

    const [result] = await pool.execute(
      'INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)',
      [name, email, hashedPassword, 'teacher']
    );

    return res.status(201).json({
      message: 'Teacher created successfully',
      user: {
        id: result.insertId,
        name,
        email,
        role: 'teacher'
      }
    });
  } catch (error) {
    console.error('createTeacher error:', error.message);
    return res.status(500).json({ message: 'Internal server error' });
  }
};

module.exports = { createTeacher };
