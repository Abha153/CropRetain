
import os
from pathlib import Path

import pandas as pd
import requests

API_URL = (
    "https://api.data.gov.in/resource/"
    "9ef84268-d588-465a-a308-a864a43d0070"
)


def main():
    api_key = os.getenv("DATA_GOV_IN_API_KEY")

    if not api_key:
        raise SystemExit(
            "API key missing. Set DATA_GOV_IN_API_KEY in PowerShell."
        )

    params = {
        "api-key": api_key,
        "format": "json",
        "offset": 0,
        "limit": 10,
    }

    print("Connecting to data.gov.in...")

    response = requests.get(
        API_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    records = payload.get("records", [])

    print("API total:", payload.get("total", "Not provided"))
    print("Records received:", len(records))

    if not records:
        print("No records received. API response:")
        print(payload)
        return

    df = pd.DataFrame(records)

    output_dir = Path(__file__).parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "mandi_sample.csv"
    df.to_csv(output_file, index=False)

    print("\nColumns found:")
    print(df.columns.tolist())

    print("\nSample records:")
    print(df.head().to_string(index=False))

    print(f"\nCSV saved to: {output_file}")


if __name__ == "__main__":
    main()
