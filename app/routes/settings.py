from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from ..db import settings_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import CurrencyRatesOut, CurrencyRatesUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

# One fixed document ID — this is a single shared, app-wide setting (not
# one per package, not one per user), so there's only ever one row to read
# or write.
CURRENCY_RATES_ID = "currency_rates"


@router.get("/currency-rates", response_model=CurrencyRatesOut)
async def get_currency_rates(user: CurrentUser = Depends(get_current_user)):
    doc = await settings_collection.find_one({"_id": CURRENCY_RATES_ID})
    if not doc:
        return CurrencyRatesOut()
    return CurrencyRatesOut(
        thaiRate=doc.get("thaiRate", ""),
        malaysianRate=doc.get("malaysianRate", ""),
        updatedAt=doc.get("updatedAt", ""),
        updatedBy=doc.get("updatedBy", ""),
    )


@router.put("/currency-rates", response_model=CurrencyRatesOut)
async def update_currency_rates(
    body: CurrencyRatesUpdate, user: CurrentUser = Depends(get_current_user)
):
    # No role check — any logged-in user (admin or not) can view and update
    # these, per the explicit request that this icon (unlike Net Profit)
    # shows for everyone.
    update = {
        "thaiRate": body.thaiRate,
        "malaysianRate": body.malaysianRate,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedBy": user.id,
    }
    await settings_collection.update_one(
        {"_id": CURRENCY_RATES_ID}, {"$set": update}, upsert=True
    )
    return CurrencyRatesOut(**update)
