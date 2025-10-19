from typing import List, Dict
from playwright.async_api import Page
import re

async def parse_table_rows(page: Page) -> List[Dict]:
    # First, try to find any "view bill" links anywhere on the page
    view_bill_links = page.locator("a").filter(has_text=re.compile("view bill", re.I))
    bill_links_count = await view_bill_links.count()

    print(f"Found {bill_links_count} 'view bill' links on the page")

    if bill_links_count > 0:
        # If we found view bill links, create records for each one
        data_rows = []
        for i in range(bill_links_count):
            link = view_bill_links.nth(i)
            href = await link.get_attribute("href")

            # Try to find the parent row to extract other information
            parent_row = link.locator("xpath=ancestor::tr[1]")
            row_data = {"detail_url": href}

            if await parent_row.count() > 0:
                cells = await parent_row.locator("td, th").all()
                for j, cell in enumerate(cells):
                    text = (await cell.inner_text()).strip()
                    row_data[f"col_{j}"] = text

                    # Try to identify common fields
                    text_lower = text.lower()
                    if "bill" in text_lower and any(char.isdigit() for char in text):
                        row_data["bill_id"] = text
                    elif "$" in text or any(text_lower.startswith(prefix) for prefix in ["amount", "balance", "due"]):
                        row_data["amount_due"] = text

            data_rows.append(row_data)

        return data_rows

    # Fallback to original table parsing if no view bill links found
    tables = page.locator("table")
    n = await tables.count()
    if n == 0:
        return []

    # Look through all tables for ones with links
    data_rows = []
    for table_idx in range(n):
        table = tables.nth(table_idx)
        rows = await table.locator("tr").all()

        # Check if this table has any links
        has_links = await table.locator("a").count() > 0

        if has_links or len(data_rows) == 0:  # Process tables with links or fallback to any table
            headers = []

            # Try to get headers
            header_row = table.locator("thead tr").first
            if await header_row.count() > 0:
                header_cells = await header_row.locator("th").all()
                headers = [(await cell.inner_text()).strip() for cell in header_cells]

            if not headers and len(rows) > 0:
                # Use first row as headers if no thead
                first_row_cells = await rows[0].locator("th, td").all()
                headers = [(await cell.inner_text()).strip() for cell in first_row_cells]
                rows = rows[1:]  # Skip header row

            # Process data rows
            for row in rows:
                cells = await row.locator("td").all()
                if not cells:
                    continue

                row_data = {}
                for i, cell in enumerate(cells):
                    label = headers[i] if i < len(headers) else f"col_{i}"
                    row_data[label] = (await cell.inner_text()).strip()

                    # Check for links in this cell
                    links = await cell.locator("a").all()
                    if links and "detail_url" not in row_data:
                        try:
                            row_data["detail_url"] = await links[0].get_attribute("href")
                        except:
                            pass

                # Map common field names
                row_data["owner_name"] = row_data.get("Owner Name") or row_data.get("Owner") or row_data.get("Owners")
                row_data["parcel_id"] = row_data.get("Tax Map #") or row_data.get("SBL") or row_data.get("Parcel")
                row_data["property_address"] = row_data.get("Property Address") or row_data.get("Location") or row_data.get("Address")
                row_data["bill_id"] = row_data.get("Bill #") or row_data.get("Bill No") or row_data.get("Bill")
                row_data["status"] = row_data.get("Status")
                row_data["amount_due"] = row_data.get("Amount Due") or row_data.get("Balance") or row_data.get("Amount")
                row_data["amount_paid"] = row_data.get("Amount Paid") or row_data.get("Paid")
                row_data["due_date"] = row_data.get("Due Date") or row_data.get("Penalty Date")

                data_rows.append(row_data)

    return data_rows
