require('dotenv').config();

const bcrypt = require('bcrypt');
const pool = require('../src/config/db');

const seedAdmin = async () => {
  try {
    const email = process.env.DEFAULT_ADMIN_EMAIL || 'admin@gmail.com';
    const plainPassword = process.env.DEFAULT_ADMIN_PASSWORD || '123456';

    const [existing] = await pool.execute('SELECT id FROM users WHERE email = ? LIMIT 1', [email]);
    if (existing.length > 0) {
      console.log('Admin already exists.');
      process.exit(0);
    }

    const hashedPassword = await bcrypt.hash(plainPassword, 12);

    await pool.execute(
      'INSERT INTO users (name, email, password, role, is_active) VALUES (?, ?, ?, ?, ?)',
      ['System Admin', email, hashedPassword, 'admin', true]
    );

    console.log('Default admin seeded successfully.');
    process.exit(0);
  } catch (error) {
    console.error('Failed to seed admin:', error.message);
    process.exit(1);
  }
};

seedAdmin();
