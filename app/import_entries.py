import argparse
import pandas as pd
from uuid import uuid4
from datetime import datetime, timezone
from app.models.schemas import Entry
from app.services.storage import save_version, resolve_id_by_name
from app.services.auth import get_user_by_token

def import_entries_from_csv(csv_path: str, token: str):
    df = pd.read_csv(csv_path)
    user = get_user_by_token(token)

    for _, row in df.iterrows():
        account_id = resolve_id_by_name("accounts", row["account_name"], "account_id")
        household_id = resolve_id_by_name("households", row["household_name"], "household_id")

        entry = Entry(
            entry_id=uuid4(),
            user_id=user["user_id"],
            account_id=account_id,
            household_id=household_id,
            account_name=row["account_name"],
            household_name=row["household_name"],
            entry_date=pd.to_datetime(row["entry_date"]).date(),
            value_date=pd.to_datetime(row["value_date"]).date(),
            type=row["type"],
            category=row["category"],
            amount=row["amount"],
            description=row.get("description", ""),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_current=True
        )

        save_version(entry, "entries", "entry_id")

    print(f"Imported {len(df)} entries from {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import entries from CSV into S3.")
    parser.add_argument("csv_path", help="Path to CSV file")
    parser.add_argument("token", help="User auth token")

    args = parser.parse_args()
    import_entries_from_csv(args.csv_path, args.token)
