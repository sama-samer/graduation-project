import bcrypt from 'bcryptjs';

async function generateHash() {
  const password = '15841';
  const hash = await bcrypt.hash(password, 10);
  console.log('Hash for password "15841":');
  console.log(hash);
}

generateHash();
