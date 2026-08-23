export const LETTER_ROWS: readonly string[][] = [
  [..."QWERTYUIOP"],
  [..."ASDFGHJKL"],
  [..."ZXCVBNM"],
];

// Always visible in both compact and full mode -- Portuguese text needs
// these too often to gate behind the "full" toggle.
export const ACCENT_ROW: readonly string[] = [..."ÁÃÂÀÉÊÍÓÔÕÚ", "Ç"];

// Full mode only, rendered above the letter grid.
export const FULL_EXTRA_ROWS: readonly string[][] = [
  [..."1234567890"],
  [",", ".", "-", "?"],
];

export function keyOutput(char: string, shiftActive: boolean): string {
  return shiftActive ? char.toUpperCase() : char.toLowerCase();
}
