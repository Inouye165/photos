import sys
from backend.vector_engine import VectorEngine
from backend.database import get_photo_by_id

ve = VectorEngine.get_instance()

queries = [
    'sunset on the ocean beach',
    'birthday cake with candles',
    'snowy mountain peak hiking',
    'dog in the park'
]

print("=== Testing Semantic Vector Search on Real Photo Index ===", flush=True)
for q in queries:
    results = ve.search_text(q, top_k=2)
    print(f"\nQuery: '{q}'", flush=True)
    for r in results:
        photo = get_photo_by_id(r['photo_id'])
        if photo:
            print(f"  -> Match: {photo['file_name']} (Similarity: {r['similarity_score']:.4f}, Camera: {photo['camera_make']} {photo['camera_model']})", flush=True)
        else:
            print(f"  -> Photo ID {r['photo_id']} (Score: {r['similarity_score']:.4f})", flush=True)
