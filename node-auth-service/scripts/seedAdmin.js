require('dotenv').config();

const bcrypt = require('bcrypt');
const pool = require('../src/config/db');

const DEMO_ACCOUNTS = [
  {
    email: 'cuong0505@gmail.com',
    password: 'cuong0505',
    name: 'Giáo viên Cường',
    role: 'teacher',
    isDemo: true,
  },
  {
    email: 'cuong0505@gmail.com',
    password: 'cuong0505',
    name: 'Học viên Cường',
    role: 'student',
    isDemo: true,
  },
];

const seedAdmin = async () => {
  try {
    const email = process.env.DEFAULT_ADMIN_EMAIL || 'admin@gmail.com';
    const plainPassword = process.env.DEFAULT_ADMIN_PASSWORD || '123456';

    const [existing] = await pool.execute('SELECT id FROM users WHERE email = ? AND role = ? LIMIT 1', [email, 'admin']);
    if (existing.length === 0) {
      const hashedPassword = await bcrypt.hash(plainPassword, 12);
      await pool.execute(
        'INSERT INTO users (name, email, password, role, is_active) VALUES (?, ?, ?, ?, ?)',
        ['System Admin', email, hashedPassword, 'admin', true]
      );
      console.log('✅ Default admin seeded successfully.');
    } else {
      console.log('⏩ Admin already exists.');
    }

    for (const acc of DEMO_ACCOUNTS) {
      const [dup] = await pool.execute('SELECT id FROM users WHERE email = ? AND role = ? LIMIT 1', [acc.email, acc.role]);
      if (dup.length > 0) {
        console.log(`⏩ Demo already exists: ${acc.email} (${acc.role})`);
        continue;
      }
      const hashed = await bcrypt.hash(acc.password, 12);
      await pool.execute(
        'INSERT INTO users (name, email, password, role, is_active, is_demo) VALUES (?, ?, ?, ?, ?, ?)',
        [acc.name, acc.email, hashed, acc.role, true, acc.isDemo]
      );
      console.log(`✅ Seeded demo: ${acc.email} (${acc.role})`);
    }

    process.exit(0);
  } catch (error) {
    console.error('Failed to seed admin/demo users:', error.message);
    process.exit(1);
  }
};

seedAdmin();
