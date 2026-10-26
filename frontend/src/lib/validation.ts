export const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function passwordStrength(password: string): 0 | 1 | 2 | 3 {
  if (password.length === 0) {
    return 0;
  }
  if (password.length < 10) {
    return 1;
  }
  const kinds = [/[a-zçğıöşü]/, /[A-ZÇĞİÖŞÜ]/, /\d/, /[^A-Za-z0-9çğıöşüÇĞİÖŞÜ]/].filter((pattern) => pattern.test(password)).length;
  return password.length >= 14 && kinds >= 3 ? 3 : 2;
}
