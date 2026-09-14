/**
 * Minimal, dependency-free QR code generator (byte mode, error-correction
 * level M, versions 1-10). A trimmed port of Nayuki's qrcodegen algorithm
 * (MIT) — enough to encode tenant portal URLs (well under 100 bytes).
 *
 * Pure JavaScript with no native modules, so it is safe to ship via OTA
 * (EAS Update) — unlike react-native-svg-based QR libraries.
 */

const MIN_VERSION = 1;
const MAX_VERSION = 10;

// EC level Medium tables, indexed by version (index 0 is padding).
const ECC_CODEWORDS_PER_BLOCK = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
const NUM_EC_BLOCKS = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
// EC level Medium has format-info bits 00.
const ECL_FORMAT_BITS = 0;

/** Number of modules usable for raw data (before ECC) for a version. */
function getNumRawDataModules(ver: number): number {
  let result = (16 * ver + 128) * ver + 64;
  if (ver >= 2) {
    const numAlign = Math.floor(ver / 7) + 2;
    result -= (25 * numAlign - 10) * numAlign - 55;
    if (ver >= 7) result -= 36;
  }
  return result;
}

function getNumDataCodewords(ver: number): number {
  return Math.floor(getNumRawDataModules(ver) / 8) - ECC_CODEWORDS_PER_BLOCK[ver] * NUM_EC_BLOCKS[ver];
}

function getAlignmentPatternPositions(ver: number): number[] {
  if (ver === 1) return [];
  const numAlign = Math.floor(ver / 7) + 2;
  const step = Math.ceil((ver * 4 + 4) / (numAlign * 2 - 2)) * 2;
  const result: number[] = [6];
  for (let i = 0, pos = ver * 4 + 10; i < numAlign - 1; i++, pos -= step) {
    result.splice(1, 0, pos);
  }
  return result;
}

// --- Reed-Solomon over GF(2^8) with primitive polynomial 0x11D -------------

function rsMultiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z;
}

function rsComputeDivisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < degree; j++) {
      result[j] = rsMultiply(result[j], root);
      if (j + 1 < degree) result[j] ^= result[j + 1];
    }
    root = rsMultiply(root, 0x02);
  }
  return result;
}

function rsComputeRemainder(data: number[], divisor: number[]): number[] {
  const result = new Array<number>(divisor.length).fill(0);
  for (const b of data) {
    const factor = b ^ (result.shift() as number);
    result.push(0);
    divisor.forEach((coef, i) => {
      result[i] ^= rsMultiply(coef, factor);
    });
  }
  return result;
}

// --- Bit-level helpers ------------------------------------------------------

function getBit(x: number, i: number): boolean {
  return ((x >>> i) & 1) !== 0;
}

function utf8Bytes(text: string): number[] {
  const bytes: number[] = [];
  for (let i = 0; i < text.length; i++) {
    let code = text.charCodeAt(i);
    if (code < 0x80) {
      bytes.push(code);
    } else if (code < 0x800) {
      bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
    } else if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
      code = 0x10000 + ((code - 0xd800) << 10) + (text.charCodeAt(++i) - 0xdc00);
      bytes.push(
        0xf0 | (code >> 18),
        0x80 | ((code >> 12) & 0x3f),
        0x80 | ((code >> 6) & 0x3f),
        0x80 | (code & 0x3f)
      );
    } else {
      bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
    }
  }
  return bytes;
}

/** ECC + block interleaving per the QR spec. */
function addEccAndInterleave(data: number[], ver: number): number[] {
  const numBlocks = NUM_EC_BLOCKS[ver];
  const blockEccLen = ECC_CODEWORDS_PER_BLOCK[ver];
  const rawCodewords = Math.floor(getNumRawDataModules(ver) / 8);
  const numShortBlocks = numBlocks - (rawCodewords % numBlocks);
  const shortBlockLen = Math.floor(rawCodewords / numBlocks);

  const rsDiv = rsComputeDivisor(blockEccLen);
  const blocks: number[][] = [];
  for (let i = 0, k = 0; i < numBlocks; i++) {
    const dat = data.slice(k, k + shortBlockLen - blockEccLen + (i < numShortBlocks ? 0 : 1));
    k += dat.length;
    const ecc = rsComputeRemainder(dat, rsDiv);
    if (i < numShortBlocks) dat.push(0);
    blocks.push(dat.concat(ecc));
  }

  const result: number[] = [];
  for (let i = 0; i < blocks[0].length; i++) {
    blocks.forEach((block, j) => {
      if (i !== shortBlockLen - blockEccLen || j >= numShortBlocks) {
        result.push(block[i]);
      }
    });
  }
  return result;
}

// --- Matrix drawing ---------------------------------------------------------

class QrMatrix {
  readonly size: number;
  readonly modules: boolean[][];
  private readonly isFunction: boolean[][];

  constructor(private readonly ver: number) {
    this.size = ver * 4 + 17;
    this.modules = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false));
    this.isFunction = Array.from({ length: this.size }, () =>
      new Array<boolean>(this.size).fill(false)
    );
  }

  drawFunctionPatterns() {
    for (let i = 0; i < this.size; i++) {
      this.setFunctionModule(6, i, i % 2 === 0);
      this.setFunctionModule(i, 6, i % 2 === 0);
    }
    this.drawFinderPattern(3, 3);
    this.drawFinderPattern(this.size - 4, 3);
    this.drawFinderPattern(3, this.size - 4);

    const alignPos = getAlignmentPatternPositions(this.ver);
    const numAlign = alignPos.length;
    for (let i = 0; i < numAlign; i++) {
      for (let j = 0; j < numAlign; j++) {
        // Skip the three corners covered by finder patterns.
        if (!((i === 0 && j === 0) || (i === 0 && j === numAlign - 1) || (i === numAlign - 1 && j === 0))) {
          this.drawAlignmentPattern(alignPos[i], alignPos[j]);
        }
      }
    }
    this.drawFormatBits(0); // Reserve format-info areas; real value drawn later.
    this.drawVersion();
  }

  drawCodewords(data: number[]) {
    let i = 0;
    for (let right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < this.size; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? this.size - 1 - vert : vert;
          if (!this.isFunction[y][x] && i < data.length * 8) {
            this.modules[y][x] = getBit(data[i >>> 3], 7 - (i & 7));
            i++;
          }
        }
      }
    }
  }

  applyMask(mask: number) {
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        if (this.isFunction[y][x]) continue;
        let invert = false;
        switch (mask) {
          case 0: invert = (x + y) % 2 === 0; break;
          case 1: invert = y % 2 === 0; break;
          case 2: invert = x % 3 === 0; break;
          case 3: invert = (x + y) % 3 === 0; break;
          case 4: invert = (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0; break;
          case 5: invert = ((x * y) % 2) + ((x * y) % 3) === 0; break;
          case 6: invert = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          case 7: invert = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0; break;
        }
        this.modules[y][x] = this.modules[y][x] !== invert;
      }
    }
  }

  drawFormatBits(mask: number) {
    const data = (ECL_FORMAT_BITS << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;

    for (let i = 0; i <= 5; i++) this.setFunctionModule(8, i, getBit(bits, i));
    this.setFunctionModule(8, 7, getBit(bits, 6));
    this.setFunctionModule(8, 8, getBit(bits, 7));
    this.setFunctionModule(7, 8, getBit(bits, 8));
    for (let i = 9; i < 15; i++) this.setFunctionModule(14 - i, 8, getBit(bits, i));

    for (let i = 0; i < 8; i++) this.setFunctionModule(this.size - 1 - i, 8, getBit(bits, i));
    for (let i = 8; i < 15; i++) this.setFunctionModule(8, this.size - 15 + i, getBit(bits, i));
    this.setFunctionModule(8, this.size - 8, true); // Always-dark module.
  }

  /** Penalty score for mask selection (lower = easier to scan). */
  getPenaltyScore(): number {
    let result = 0;
    const size = this.size;

    // Adjacent runs of the same colour, rows then columns.
    for (const horizontal of [true, false]) {
      for (let a = 0; a < size; a++) {
        let runColor = false;
        let runLen = 0;
        for (let b = 0; b < size; b++) {
          const color = horizontal ? this.modules[a][b] : this.modules[b][a];
          if (b === 0 || color !== runColor) {
            runColor = color;
            runLen = 1;
          } else {
            runLen++;
            if (runLen === 5) result += 3;
            else if (runLen > 5) result++;
          }
        }
      }
    }

    // 2x2 solid blocks.
    for (let y = 0; y < size - 1; y++) {
      for (let x = 0; x < size - 1; x++) {
        const c = this.modules[y][x];
        if (c === this.modules[y][x + 1] && c === this.modules[y + 1][x] && c === this.modules[y + 1][x + 1]) {
          result += 3;
        }
      }
    }

    // Dark/light balance.
    let dark = 0;
    for (const row of this.modules) for (const cell of row) if (cell) dark++;
    const total = size * size;
    const k = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
    result += k * 10;
    return result;
  }

  private setFunctionModule(x: number, y: number, isDark: boolean) {
    this.modules[y][x] = isDark;
    this.isFunction[y][x] = true;
  }

  private drawFinderPattern(x: number, y: number) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const xx = x + dx;
        const yy = y + dy;
        if (xx >= 0 && xx < this.size && yy >= 0 && yy < this.size) {
          const dist = Math.max(Math.abs(dx), Math.abs(dy));
          this.setFunctionModule(xx, yy, dist !== 2 && dist !== 4);
        }
      }
    }
  }

  private drawAlignmentPattern(x: number, y: number) {
    for (let dy = -2; dy <= 2; dy++) {
      for (let dx = -2; dx <= 2; dx++) {
        this.setFunctionModule(x + dx, y + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }
  }

  private drawVersion() {
    if (this.ver < 7) return;
    let rem = this.ver;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (this.ver << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const bit = getBit(bits, i);
      const a = this.size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      this.setFunctionModule(a, b, bit);
      this.setFunctionModule(b, a, bit);
    }
  }
}

/**
 * Generate a QR matrix for the given text. Returns `modules[y][x]` booleans
 * (true = dark). Throws if the text exceeds the supported capacity (~213
 * bytes) — portal URLs are far below that.
 */
export function generateQrMatrix(text: string): boolean[][] {
  const dataBytes = utf8Bytes(text);

  let ver = -1;
  for (let v = MIN_VERSION; v <= MAX_VERSION; v++) {
    const charCountBits = v <= 9 ? 8 : 16;
    if (4 + charCountBits + dataBytes.length * 8 <= getNumDataCodewords(v) * 8) {
      ver = v;
      break;
    }
  }
  if (ver === -1) throw new Error("Text too long for a QR code");

  // Byte-mode segment: mode 0100, char count, data, terminator, padding.
  const capacityBits = getNumDataCodewords(ver) * 8;
  const bb: { val: number; len: number }[] = [];
  bb.push({ val: 0x4, len: 4 });
  bb.push({ val: dataBytes.length, len: ver <= 9 ? 8 : 16 });
  for (const b of dataBytes) bb.push({ val: b, len: 8 });

  let bitLen = bb.reduce((sum, b) => sum + b.len, 0);
  const terminator = Math.min(4, capacityBits - bitLen);
  bb.push({ val: 0, len: terminator });
  bitLen += terminator;
  bb.push({ val: 0, len: (8 - (bitLen % 8)) % 8 });

  const data: number[] = [];
  let acc = 0;
  let accLen = 0;
  for (const { val, len } of bb) {
    acc = (acc << len) | val;
    accLen += len;
    while (accLen >= 8) {
      accLen -= 8;
      data.push((acc >>> accLen) & 0xff);
    }
  }
  for (let pad = 0xec; data.length < getNumDataCodewords(ver); pad ^= 0xec ^ 0x11) {
    data.push(pad);
  }

  const allCodewords = addEccAndInterleave(data, ver);
  const qr = new QrMatrix(ver);
  qr.drawFunctionPatterns();
  qr.drawCodewords(allCodewords);

  let bestMask = 0;
  let bestPenalty = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    qr.applyMask(mask);
    qr.drawFormatBits(mask);
    const penalty = qr.getPenaltyScore();
    if (penalty < bestPenalty) {
      bestMask = mask;
      bestPenalty = penalty;
    }
    qr.applyMask(mask); // Undo; the winning mask is applied once below.
  }
  qr.applyMask(bestMask);
  qr.drawFormatBits(bestMask);

  return qr.modules;
}
