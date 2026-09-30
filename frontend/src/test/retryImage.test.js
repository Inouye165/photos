import { describe, expect, it } from 'vitest';
import { getPhotoImageSource } from '../components/RetryImage';

describe('getPhotoImageSource', () => {
  it('progresses through refresh and original fallbacks', () => {
    expect(getPhotoImageSource(9352, 0)).toBe('/api/photos/9352/thumbnail');
    expect(getPhotoImageSource(9352, 1)).toBe('/api/photos/9352/thumbnail?refresh=true');
    expect(getPhotoImageSource(9352, 2)).toBe('/api/photos/9352/original');
    expect(getPhotoImageSource(9352, 3)).toBe('/api/photos/9352/original?retry=1');
    expect(getPhotoImageSource(9352, 4)).toBeNull();
  });
});