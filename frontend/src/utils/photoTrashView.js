export function createOptimisticTrashState(photos, photoIds, totalPhotos) {
  const trashedIds = new Set(photoIds);
  const remainingPhotos = photos.filter((photo) => !trashedIds.has(photo.id));
  const removedCount = photos.length - remainingPhotos.length;
  const nextTotal = Math.max(0, totalPhotos - removedCount);

  return {
    photos: remainingPhotos,
    removedCount,
    totalPhotos: nextTotal,
    hasMore: remainingPhotos.length < nextTotal
  };
}

export function canLoadMorePhotos({
  photoCount,
  totalPhotos,
  hasMore,
  isLoading,
  isLoadingMore,
  hasPendingTrash
}) {
  return (
    photoCount > 0 &&
    totalPhotos > photoCount &&
    hasMore &&
    !isLoading &&
    !isLoadingMore &&
    !hasPendingTrash
  );
}

export function mergeUniquePhotos(existingPhotos, incomingPhotos) {
  const knownIds = new Set(existingPhotos.map((photo) => photo.id));
  const uniqueIncoming = incomingPhotos.filter((photo) => {
    if (knownIds.has(photo.id)) return false;
    knownIds.add(photo.id);
    return true;
  });

  return [...existingPhotos, ...uniqueIncoming];
}

export function mergePhotoPage(existingPhotos, incomingPhotos, totalPhotos) {
  const photos = mergeUniquePhotos(existingPhotos, incomingPhotos);
  return {
    photos,
    hasMore: photos.length < totalPhotos
  };
}

export function excludePhotosById(photos, excludedPhotoIds) {
  if (!excludedPhotoIds || excludedPhotoIds.size === 0) return photos;
  return photos.filter((photo) => !excludedPhotoIds.has(photo.id));
}

export function createLatestRequestGuard() {
  let version = 0;

  return {
    current: () => version,
    invalidate: () => {
      version += 1;
      return version;
    },
    isCurrent: (requestVersion) => requestVersion === version
  };
}

export function createPendingTrashTracker() {
  const pendingIds = new Set();
  const activeIds = new Set();

  return {
    begin: (photoIds) => {
      for (const photoId of photoIds) {
        pendingIds.add(photoId);
        activeIds.add(photoId);
      }
    },
    finishMutation: (photoIds) => {
      for (const photoId of photoIds) activeIds.delete(photoId);
    },
    activeIds: () => new Set(activeIds),
    pendingIds: () => new Set(pendingIds),
    hasPending: () => pendingIds.size > 0,
    resolveLoadedView: () => {
      if (activeIds.size === 0) pendingIds.clear();
    }
  };
}

export async function loadPhotoWindow({
  fetchPage,
  queryOptions,
  targetCount,
  pageSize,
  excludedPhotoIds = new Set(),
  shouldContinue = () => true
}) {
  let photos = [];
  let totalPhotos = targetCount;
  let sourceOffset = 0;
  let sourceTotal = targetCount;
  let parsedQuery = null;
  const excludedIds = new Set(excludedPhotoIds);
  const excludedIdsSeen = new Set();

  while (
    shouldContinue() &&
    sourceOffset < sourceTotal &&
    photos.length < Math.min(targetCount, totalPhotos)
  ) {
    const requestLimit = Math.min(pageSize, targetCount - photos.length);
    const data = await fetchPage({
      ...queryOptions,
      limit: requestLimit,
      offset: sourceOffset
    });
    if (!shouldContinue()) return null;

    const sourcePhotos = data.photos || [];
    sourceOffset += sourcePhotos.length;
    sourceTotal = data.total ?? sourceTotal;
    for (const photo of sourcePhotos) {
      if (excludedIds.has(photo.id)) excludedIdsSeen.add(photo.id);
    }
    totalPhotos = Math.max(0, sourceTotal - excludedIdsSeen.size);
    const visiblePhotos = excludePhotosById(sourcePhotos, excludedIds);
    const pageState = mergePhotoPage(photos, visiblePhotos, totalPhotos);
    parsedQuery = data.parsed_query ?? parsedQuery;
    photos = pageState.photos;
    if (sourcePhotos.length === 0) break;
  }

  return {
    photos,
    totalPhotos,
    hasMore: photos.length < totalPhotos,
    parsedQuery
  };
}

export function capturePhotoViewportAnchor(
  root,
  excludedPhotoIds,
  { viewportTop = 0, viewportBottom = globalThis.innerHeight ?? Infinity } = {}
) {
  if (!root?.querySelectorAll) return null;

  const excludedIds = new Set(Array.from(excludedPhotoIds, String));
  const cards = root.querySelectorAll('[data-photo-id]');
  let nearestSurvivorAbove = null;

  for (const card of cards) {
    const photoId = card.dataset?.photoId;
    if (!photoId || excludedIds.has(photoId)) continue;

    const bounds = card.getBoundingClientRect();
    if (bounds.bottom > viewportTop && bounds.top < viewportBottom) {
      return { photoId, top: bounds.top };
    }
    if (bounds.top >= viewportBottom) {
      return { photoId, top: viewportTop };
    }
    nearestSurvivorAbove = photoId;
  }

  return nearestSurvivorAbove === null
    ? null
    : { photoId: nearestSurvivorAbove, top: viewportTop };
}

export function restorePhotoViewportAnchor(root, anchor, scrollBy) {
  const scrollViewport = scrollBy || ((options) => globalThis.scrollBy(options));
  if (!root?.querySelectorAll || !anchor || typeof scrollViewport !== 'function') return false;

  const cards = root.querySelectorAll('[data-photo-id]');
  const anchorCard = Array.from(cards).find(
    (card) => card.dataset?.photoId === String(anchor.photoId)
  );
  if (!anchorCard) return false;

  const offset = anchorCard.getBoundingClientRect().top - anchor.top;
  if (Math.abs(offset) >= 0.5) {
    scrollViewport({ top: offset, left: 0, behavior: 'auto' });
  }
  return true;
}