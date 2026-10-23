// Tests for the colour tokens of dark mode (styles/tokens.css): every token
// has a light and a dark value, and every token the code uses exists (a
// typo would silently lose the colour).

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(import.meta.dirname, '..');
const tokens = readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8');
const [light, dark] = tokens.split(":root[data-mantine-color-scheme='dark']");

// The token names defined in one block of tokens.css.
function defined(block) {
  return new Set([...block.matchAll(/--cv-([a-z0-9-]+):/g)].map((match) => match[1]));
}

// Every .css, .jsx and .js file under src (not the tests).
function sourceFiles(folder) {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(css|jsx|js)$/.test(name) && !name.includes('.test.') ? [path] : [];
  });
}

describe('colour tokens', () => {
  it('has a dark value for every light value', () => {
    expect(defined(light).size).toBeGreaterThan(40);
    expect([...defined(dark)].sort()).toEqual([...defined(light)].sort());
  });

  it('defines every token the code uses', () => {
    const known = defined(light);
    const unknown = [];
    for (const file of sourceFiles(SRC)) {
      for (const match of readFileSync(file, 'utf8').matchAll(/var\(--cv-([a-z0-9-]+)\)/g)) {
        if (!known.has(match[1])) unknown.push(`${file}: --cv-${match[1]}`);
      }
    }
    expect(unknown).toEqual([]);
  });
});
