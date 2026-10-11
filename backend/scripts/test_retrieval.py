import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.retrieval import build_index, search

METADATA_PATH = ROOT / "data" / "app_metadata.json"
SAMPLE_QUERIES = [
    "revenue performance across regions",
    "compare sales trends by product category",
    "which sales channels contribute most to revenue",
    "track quarterly revenue against last quarter",
    "monitor inventory levels and stock alerts",
    "which products are running low on stock",
    "review operating expenses and freight costs",
    "compare expense trends by region",
    "identify customers with repeat purchases",
    "analyze customer retention and churn risk",
    "measure sales target attainment by territory",
    "review order fulfillment and on-time delivery",
]


def main() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    build_index(metadata)

    for query in SAMPLE_QUERIES:
        print(f"\nQuery: {query}")
        for result in search(query, k=3):
            print(
                f"  {result['score']:.4f} | {result['type']} | "
                f"{result['breadcrumb']} | {result['title']}"
            )


if __name__ == "__main__":
    main()
