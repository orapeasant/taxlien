import os
RATE_MS = int(os.getenv("BAS_RATE_DELAY_MS","1500"))
SNAPSHOT = os.getenv("BAS_SNAPSHOT_HTML","false").lower()=="true"
