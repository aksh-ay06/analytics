"""
Full pipeline entry point.
Runs ingestion → transforms → metrics in sequence.
"""

from pipeline.ingest import run_ingestion
from pipeline.transform import run_transforms
from pipeline.metrics import run_metrics

if __name__ == "__main__":
    print("=== Step 1: Ingestion ===")
    con = run_ingestion()

    print("\n=== Step 2: Transforms ===")
    run_transforms(con)

    print("\n=== Step 3: Metrics ===")
    run_metrics(con)

    print("\nPipeline complete.")
    con.close()
