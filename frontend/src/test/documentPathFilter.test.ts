import { describe, it, expect } from 'vitest';
import {
  normalizePath,
  isPathWithin,
  isPathWithinAllowedRoots,
  validateFolderToWatch
} from '../utils/documentPathFilter';
import { AllowedRoot } from '../types/documents';

describe('documentPathFilter - TypeScript Regression Test Suite', () => {
  const mockAllowedRoots: AllowedRoot[] = [
    {
      key: 'windows_documents',
      name: 'Windows Documents',
      path: 'C:\\Users\\inouy\\Documents',
      exists: true,
      source: 'Windows'
    },
    {
      key: 'windows_downloads',
      name: 'Windows Downloads',
      path: 'C:\\Users\\inouy\\Downloads',
      exists: true,
      source: 'Windows'
    },
    {
      key: 'onedrive_documents',
      name: 'OneDrive Documents',
      path: 'C:\\Users\\inouy\\OneDrive\\Documents',
      exists: true,
      source: 'OneDrive'
    },
    {
      key: 'onedrive_downloads',
      name: 'OneDrive Downloads',
      path: 'C:\\Users\\inouy\\OneDrive\\Downloads',
      exists: true,
      source: 'OneDrive'
    }
  ];

  describe('normalizePath', () => {
    it('converts Windows backslashes to forward slashes', () => {
      expect(normalizePath('C:\\Users\\inouy\\Documents')).toBe('C:/Users/inouy/Documents');
    });

    it('removes trailing slashes', () => {
      expect(normalizePath('C:/Users/inouy/Documents/')).toBe('C:/Users/inouy/Documents');
      expect(normalizePath('C:\\Users\\inouy\\Downloads\\\\')).toBe('C:/Users/inouy/Downloads');
    });

    it('normalizes path traversal .. segments', () => {
      expect(normalizePath('C:\\Users\\inouy\\Documents\\..\\Desktop')).toBe('C:/Users/inouy/Desktop');
    });

    it('collapses consecutive slashes', () => {
      expect(normalizePath('C:\\Users\\\\inouy///Documents')).toBe('C:/Users/inouy/Documents');
    });
  });

  describe('isPathWithin', () => {
    it('returns true for exact directory match', () => {
      expect(isPathWithin('C:\\Users\\inouy\\Documents', 'C:\\Users\\inouy\\Documents')).toBe(true);
    });

    it('returns true for nested subdirectories', () => {
      expect(isPathWithin('C:\\Users\\inouy\\Documents\\Taxes\\2025', 'C:\\Users\\inouy\\Documents')).toBe(true);
      expect(isPathWithin('C:/Users/inouy/Documents/Work/Contract.pdf', 'C:\\Users\\inouy\\Documents')).toBe(true);
    });

    it('is case-insensitive on Windows paths', () => {
      expect(isPathWithin('c:\\users\\inouy\\documents\\file.txt', 'C:\\Users\\inouy\\Documents')).toBe(true);
    });

    it('does not false-match when another folder shares name prefix', () => {
      // DocumentsArchive should NOT be considered inside Documents
      expect(isPathWithin('C:\\Users\\inouy\\DocumentsArchive', 'C:\\Users\\inouy\\Documents')).toBe(false);
      expect(isPathWithin('C:\\Users\\inouy\\DownloadsOld', 'C:\\Users\\inouy\\Downloads')).toBe(false);
    });

    it('returns false when candidate is parent of root', () => {
      expect(isPathWithin('C:\\Users\\inouy', 'C:\\Users\\inouy\\Documents')).toBe(false);
    });
  });

  describe('isPathWithinAllowedRoots', () => {
    it('allows paths in Windows Documents', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Documents\\MyReport.pdf', mockAllowedRoots)).toBe(true);
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Documents\\Subfolder', mockAllowedRoots)).toBe(true);
    });

    it('allows paths in Windows Downloads', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Downloads\\Invoice.pdf', mockAllowedRoots)).toBe(true);
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Downloads\\2026\\Q1', mockAllowedRoots)).toBe(true);
    });

    it('allows paths in OneDrive Documents', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\OneDrive\\Documents\\Notes.docx', mockAllowedRoots)).toBe(true);
    });

    it('allows paths in OneDrive Downloads', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\OneDrive\\Downloads\\Ebook.epub', mockAllowedRoots)).toBe(true);
    });

    it('STRICTLY REJECTS Desktop', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Desktop\\Secret.pdf', mockAllowedRoots)).toBe(false);
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\OneDrive\\Desktop\\file.pdf', mockAllowedRoots)).toBe(false);
    });

    it('STRICTLY REJECTS System folders and program files', () => {
      expect(isPathWithinAllowedRoots('C:\\Windows\\System32\\license.rtf', mockAllowedRoots)).toBe(false);
      expect(isPathWithinAllowedRoots('C:\\Program Files\\App\\doc.pdf', mockAllowedRoots)).toBe(false);
      expect(isPathWithinAllowedRoots('C:\\', mockAllowedRoots)).toBe(false);
    });

    it('STRICTLY REJECTS path traversal escape attempts', () => {
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Documents\\..\\Desktop\\file.pdf', mockAllowedRoots)).toBe(false);
      expect(isPathWithinAllowedRoots('C:\\Users\\inouy\\Downloads\\..\\AppData\\Local\\doc.txt', mockAllowedRoots)).toBe(false);
    });
  });

  describe('validateFolderToWatch', () => {
    it('approves folders inside allowed roots', () => {
      const result = validateFolderToWatch('C:\\Users\\inouy\\Documents\\Personal', mockAllowedRoots);
      expect(result.valid).toBe(true);
      expect(result.matchedRoot?.key).toBe('windows_documents');
    });

    it('approves OneDrive folders', () => {
      const result = validateFolderToWatch('C:\\Users\\inouy\\OneDrive\\Documents\\Archive', mockAllowedRoots);
      expect(result.valid).toBe(true);
      expect(result.matchedRoot?.key).toBe('onedrive_documents');
    });

    it('rejects unauthorized paths with clear descriptive error message', () => {
      const result = validateFolderToWatch('C:\\Users\\inouy\\Desktop', mockAllowedRoots);
      expect(result.valid).toBe(false);
      expect(result.reason).toContain('Forbidden');
      expect(result.reason).toContain('Documents and Downloads');
    });

    it('rejects empty input', () => {
      const result = validateFolderToWatch('   ', mockAllowedRoots);
      expect(result.valid).toBe(false);
      expect(result.reason).toBe('Please provide a folder path.');
    });
  });
});
