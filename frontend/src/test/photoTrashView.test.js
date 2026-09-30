import { describe, expect, it, vi } from 'vitest';
import {
  canLoadMorePhotos,
  capturePhotoViewportAnchor,
  createLatestRequestGuard,
  createOptimisticTrashState,
  createPendingTrashTracker,
  excludePhotosById,
  loadPhotoWindow,
  mergePhotoPage,
  mergeUniquePhotos,
  restorePhotoViewportAnchor
} from '../utils/photoTrashView';

function photoCard(photoId, top, bottom) {
  return {
    dataset: { photoId: String(photoId) },
    getBoundingClientRect: () => ({ top, bottom })
  };
}

function photoGrid(cards) {
  return {
    querySelectorAll: () => cards
  };
}

describe('photo trash view state', () => {
  it('blocks infinite scroll until the initial page establishes an authoritative total', () => {
    expect(canLoadMorePhotos({
      photoCount: 0,
      totalPhotos: 0,
      hasMore: true,
      isLoading: false,
      isLoadingMore: false,
      hasPendingTrash: false
    })).toBe(false);
  });

  it('allows infinite scroll after the first page confirms more photos exist', () => {
    expect(canLoadMorePhotos({
      photoCount: 80,
      totalPhotos: 3123,
      hasMore: true,
      isLoading: false,
      isLoadingMore: false,
      hasPendingTrash: false
    })).toBe(true);
  });

  it('removes selected photos immediately and updates the loaded range totals', () => {
    const photos = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];

    expect(createOptimisticTrashState(photos, [2, 4], 10)).toEqual({
      photos: [{ id: 1 }, { id: 3 }],
      removedCount: 2,
      totalPhotos: 8,
      hasMore: true
    });
  });

  it('does not reduce totals for IDs that are absent from the loaded photos', () => {
    const state = createOptimisticTrashState([{ id: 1 }], [99], 1);

    expect(state).toEqual({
      photos: [{ id: 1 }],
      removedCount: 0,
      totalPhotos: 1,
      hasMore: false
    });
  });

  it('merges replacement photos without duplicating existing or incoming IDs', () => {
    expect(mergeUniquePhotos(
      [{ id: 1 }, { id: 2 }],
      [{ id: 2 }, { id: 3 }, { id: 3 }, { id: 4 }]
    )).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }]);
  });

  it('keeps pagination open when an overlapping page adds fewer unique photos', () => {
    expect(mergePhotoPage(
      [{ id: 1 }, { id: 2 }],
      [{ id: 2 }, { id: 3 }],
      4
    )).toEqual({
      photos: [{ id: 1 }, { id: 2 }, { id: 3 }],
      hasMore: true
    });
  });

  it('excludes pending trash IDs from fetched photos', () => {
    expect(excludePhotosById(
      [{ id: 1 }, { id: 2 }, { id: 3 }],
      new Set([2])
    )).toEqual([{ id: 1 }, { id: 3 }]);
  });
});

describe('photo request coordination', () => {
  it('rejects a deferred page response after the active photo view is invalidated', async () => {
    const guard = createLatestRequestGuard();
    const requestVersion = guard.invalidate();
    let resolveRequest;
    const deferredRequest = new Promise((resolve) => {
      resolveRequest = resolve;
    });
    const guardedResult = deferredRequest.then((result) => (
      guard.isCurrent(requestVersion) ? result : null
    ));

    guard.invalidate();
    resolveRequest([{ id: 1 }]);

    await expect(guardedResult).resolves.toBeNull();
  });

  it('rebuilds a reordered loaded window from offset zero', async () => {
    const fetchPage = vi.fn()
      .mockResolvedValueOnce({ photos: [{ id: 3 }, { id: 1 }], total: 3 })
      .mockResolvedValueOnce({ photos: [{ id: 4 }], total: 3 });

    const state = await loadPhotoWindow({
      fetchPage,
      queryOptions: { sortBy: 'date_taken' },
      targetCount: 4,
      pageSize: 2
    });

    expect(fetchPage).toHaveBeenNthCalledWith(1, {
      sortBy: 'date_taken',
      limit: 2,
      offset: 0
    });
    expect(fetchPage).toHaveBeenNthCalledWith(2, {
      sortBy: 'date_taken',
      limit: 2,
      offset: 2
    });
    expect(state).toEqual({
      photos: [{ id: 3 }, { id: 1 }, { id: 4 }],
      totalPhotos: 3,
      hasMore: false,
      parsedQuery: null
    });
  });

  it('discards a paged window when its request is invalidated', async () => {
    const guard = createLatestRequestGuard();
    const requestVersion = guard.invalidate();
    let resolvePage;
    const fetchPage = vi.fn(() => new Promise((resolve) => {
      resolvePage = resolve;
    }));
    const loading = loadPhotoWindow({
      fetchPage,
      queryOptions: {},
      targetCount: 2,
      pageSize: 1,
      shouldContinue: () => guard.isCurrent(requestVersion)
    });

    guard.invalidate();
    resolvePage({ photos: [{ id: 1 }], total: 2 });

    await expect(loading).resolves.toBeNull();
    expect(fetchPage).toHaveBeenCalledOnce();
  });

  it('never reintroduces pending trash IDs from a deferred refresh', async () => {
    let resolveRefresh;
    const fetchPage = vi.fn(() => new Promise((resolve) => {
      resolveRefresh = resolve;
    }));
    const refresh = loadPhotoWindow({
      fetchPage,
      queryOptions: {},
      targetCount: 3,
      pageSize: 3,
      excludedPhotoIds: new Set([2])
    });

    resolveRefresh({ photos: [{ id: 1 }, { id: 2 }, { id: 3 }], total: 3 });

    await expect(refresh).resolves.toEqual({
      photos: [{ id: 1 }, { id: 3 }],
      totalPhotos: 2,
      hasMore: false,
      parsedQuery: null
    });
  });

  it('advances source offsets when pending trash IDs are filtered out', async () => {
    const fetchPage = vi.fn()
      .mockResolvedValueOnce({ photos: [{ id: 1 }, { id: 2 }], total: 4 })
      .mockResolvedValueOnce({ photos: [{ id: 3 }, { id: 4 }], total: 4 });

    const state = await loadPhotoWindow({
      fetchPage,
      queryOptions: {},
      targetCount: 3,
      pageSize: 2,
      excludedPhotoIds: new Set([2])
    });

    expect(fetchPage).toHaveBeenNthCalledWith(2, { limit: 2, offset: 2 });
    expect(state.photos).toEqual([{ id: 1 }, { id: 3 }, { id: 4 }]);
  });

  it('retains unresolved IDs until an authoritative reload succeeds', () => {
    const tracker = createPendingTrashTracker();

    tracker.begin([2]);
    expect(tracker.activeIds()).toEqual(new Set([2]));
    expect(tracker.pendingIds()).toEqual(new Set([2]));

    tracker.finishMutation([2]);
    expect(tracker.activeIds()).toEqual(new Set());
    expect(tracker.hasPending()).toBe(true);

    tracker.resolveLoadedView();
    expect(tracker.hasPending()).toBe(false);
  });

  it('does not resolve pending IDs while another trash mutation is active', () => {
    const tracker = createPendingTrashTracker();

    tracker.begin([2]);
    tracker.begin([3]);
    tracker.finishMutation([2]);
    tracker.resolveLoadedView();

    expect(tracker.pendingIds()).toEqual(new Set([2, 3]));
    expect(tracker.activeIds()).toEqual(new Set([3]));
  });
});

describe('photo trash viewport anchoring', () => {
  it('captures the first surviving card visible below the sticky header', () => {
    const root = photoGrid([
      photoCard(1, 10, 60),
      photoCard(2, 50, 150),
      photoCard(3, 50, 150),
      photoCard(4, 900, 1000)
    ]);

    expect(capturePhotoViewportAnchor(root, new Set([2]), {
      viewportTop: 72,
      viewportBottom: 800
    })).toEqual({ photoId: '3', top: 50 });
  });

  it('anchors the next survivor to the viewport top when all visible cards are selected', () => {
    const root = photoGrid([
      photoCard(1, 50, 150),
      photoCard(2, 160, 260),
      photoCard(3, 900, 1000)
    ]);

    expect(capturePhotoViewportAnchor(root, [1, 2], {
      viewportTop: 72,
      viewportBottom: 800
    })).toEqual({ photoId: '3', top: 72 });
  });

  it('restores the surviving card to its previous screen position', () => {
    const root = photoGrid([photoCard(3, 170, 270)]);
    const scrollBy = vi.fn();

    expect(restorePhotoViewportAnchor(root, { photoId: '3', top: 50 }, scrollBy)).toBe(true);
    expect(scrollBy).toHaveBeenCalledWith({ top: 120, left: 0, behavior: 'auto' });
  });

  it('calls the browser scroll function with its global receiver', () => {
    const originalScrollBy = globalThis.scrollBy;
    const scrollBy = vi.fn(function verifyReceiver() {
      expect(this).toBe(globalThis);
    });
    globalThis.scrollBy = scrollBy;

    try {
      restorePhotoViewportAnchor(photoGrid([photoCard(3, 170, 270)]), {
        photoId: '3',
        top: 50
      });
      expect(scrollBy).toHaveBeenCalledOnce();
    } finally {
      globalThis.scrollBy = originalScrollBy;
    }
  });

  it('does nothing when the anchor photo is no longer rendered', () => {
    const scrollBy = vi.fn();

    expect(restorePhotoViewportAnchor(
      photoGrid([photoCard(4, 50, 150)]),
      { photoId: '3', top: 50 },
      scrollBy
    )).toBe(false);
    expect(scrollBy).not.toHaveBeenCalled();
  });
});