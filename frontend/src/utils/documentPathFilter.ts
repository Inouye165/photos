/**
 * Utility functions in TypeScript for enforcing strict document folder boundaries:
 * Only folders within Documents and Downloads (Windows & OneDrive) are permitted.
 */

import { AllowedRoot } from '../types/documents';

/**
 * Normalizes a Windows filesystem path: converts backslashes to forward slashes,
 * strips trailing slashes, and resolves simple relative path segments.
 */
export function normalizePath(pathStr: string): string {
  if (!pathStr || typeof pathStr !== 'string') return '';
  let clean = pathStr.trim().replace(/\\/g, '/');

  // Collapse multiple slashes
  clean = clean.replace(/\/+/g, '/');

  // Resolve relative segments (e.g. a/b/../c -> a/c)
  const segments = clean.split('/');
  const resolved: string[] = [];
  for (const seg of segments) {
    if (seg === '.' || seg === '') continue;
    if (seg === '..') {
      if (resolved.length > 0) {
        resolved.pop();
      }
    } else {
      resolved.push(seg);
    }
  }

  // Preserve drive letter e.g. C:
  const isDrive = /^[a-zA-Z]:/.test(clean);
  const prefix = isDrive ? resolved.shift() + '/' : (clean.startsWith('/') ? '/' : '');
  let result = prefix + resolved.join('/');
  if (result.endsWith('/') && result.length > 3) {
    result = result.slice(0, -1);
  }
  return result;
}

/**
 * Checks whether candidatePath resides inside or is identical to parentPath.
 * Case-insensitive comparison tailored for Windows environments.
 */
export function isPathWithin(candidatePath: string, parentPath: string): boolean {
  if (!candidatePath || !parentPath) return false;
  const normCandidate = normalizePath(candidatePath).toLowerCase();
  const normParent = normalizePath(parentPath).toLowerCase();

  if (normCandidate === normParent) return true;
  return normCandidate.startsWith(normParent.endsWith('/') ? normParent : normParent + '/');
}

/**
 * Verifies if candidatePath is within any of the permitted allowed roots.
 */
export function isPathWithinAllowedRoots(
  candidatePath: string,
  allowedRoots: Array<string | AllowedRoot>
): boolean {
  if (!candidatePath || !allowedRoots || allowedRoots.length === 0) return false;

  for (const item of allowedRoots) {
    const rootPath = typeof item === 'string' ? item : item.path;
    if (rootPath && isPathWithin(candidatePath, rootPath)) {
      return true;
    }
  }
  return false;
}

/**
 * Validates a folder path for watching, returning a descriptive result.
 */
export function validateFolderToWatch(
  folderPath: string,
  allowedRoots: AllowedRoot[]
): { valid: boolean; reason?: string; matchedRoot?: AllowedRoot } {
  if (!folderPath || !folderPath.trim()) {
    return { valid: false, reason: 'Please provide a folder path.' };
  }

  const trimmed = folderPath.trim();
  const matched = allowedRoots.find(r => isPathWithin(trimmed, r.path));

  if (!matched) {
    return {
      valid: false,
      reason: 'Forbidden: Only folders within Documents and Downloads (in Windows or OneDrive) can be watched or scanned.'
    };
  }

  return { valid: true, matchedRoot: matched };
}
