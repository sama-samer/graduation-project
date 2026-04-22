// Generate SHA-256 hash for password "15841"
async function generateHash() {
  const password = '15841';
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  console.log('SHA-256 hash for password "15841":');
  console.log(hashHex);
}

generateHash();
