import os, pathlib
from datetime import datetime
import pandas as pd

def _ensure_dir(p):
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)

async def save_snapshot(page) -> str:
    p = f"data/snapshots/{datetime.utcnow().strftime('%Y%m%dT%H%M%S%f')}.html"
    _ensure_dir("data/snapshots")
    html = await page.content()
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p

async def persist_rows(rows):
    _ensure_dir("data/exports")
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = f"data/exports/bas_all_records_{stamp}.xlsx"
    if not rows:
        return

    # Convert to DataFrame and export to Excel
    df = pd.DataFrame(rows)

    # Reorder columns to put important ones first including payment status information
    important_cols = ['municipality_slug', 'collection', 'is_unpaid', 'payment_type', 'bill_status',
                     'owner_name', 'property_address', 'parcel_id', 'bill_id', 'swis',
                     'amount_due', 'total_taxes', 'amount_paid', 'due_date', 'search_address', 'extracted_at']

    # Get existing columns in the dataframe
    existing_cols = [col for col in important_cols if col in df.columns]
    other_cols = [col for col in df.columns if col not in important_cols]

    # Reorder columns
    df = df[existing_cols + other_cols]

    # Export to Excel with formatting
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Tax Liens', index=False)

        # Get the workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets['Tax Liens']

        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
            worksheet.column_dimensions[column_letter].width = adjusted_width

    print(f"Exported {len(rows)} tax records (both paid and unpaid) to {path}")
