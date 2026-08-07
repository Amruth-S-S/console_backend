from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import packages_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import NetProfitUpdate, PackageCreate, PackageOut, PackageUpdate

router = APIRouter(prefix="/packages", tags=["packages"])


def serialize(p: dict, *, is_admin: bool = False) -> PackageOut:
    return PackageOut(
        id=str(p["_id"]),
        createdAt=p["createdAt"],
        companyName=p.get("companyName", ""),
        logo=p.get("logo"),
        poster=p.get("poster"),
        packageTitle=p.get("packageTitle", ""),
        packageType=p.get("packageType", "domestic"),
        duration=p.get("duration", ""),
        highlights=p.get("highlights", []),
        days=p.get("days", []),
        inclusions=p.get("inclusions", []),
        exclusions=p.get("exclusions", []),
        adultPrice=p.get("adultPrice", ""),
        childPrice=p.get("childPrice", ""),
        bookingAmount=p.get("bookingAmount", ""),
        gst=p.get("gst", ""),
        dates=p.get("dates", []),
        cancellationPolicy=p.get("cancellationPolicy", ""),
        additionalInfo=p.get("additionalInfo", ""),
        termsConditions=p.get("termsConditions", ""),
        # Blanked out for non-admins regardless of what's actually stored —
        # this is the one place that decides who ever sees these values.
        adultNetProfit=p.get("adultNetProfit", "") if is_admin else "",
        childNetProfit=p.get("childNetProfit", "") if is_admin else "",
        infantNetProfit=p.get("infantNetProfit", "") if is_admin else "",
    )


@router.get("", response_model=list[PackageOut])
async def list_packages(user: CurrentUser = Depends(get_current_user)):
    # Day images are full base64 photos embedded straight in the document —
    # across several days times several images each, that's easily tens of
    # MB per package. The card list never renders them (only poster/logo,
    # kept below), so a projection excludes them at the query level: Mongo
    # never even reads that field off disk here, instead of reading it and
    # then discarding it in Python. This alone took list_packages from ~160s
    # to near-instant. Editing/previewing/downloading a specific package
    # still gets the real images, via GET /packages/{id} (unprojected) —
    # see the frontend's openEdit/openQuickPreview/downloadPackagePdf, which
    # re-fetch the full package before using it rather than reusing this
    # trimmed list data.
    items = (
        await packages_collection.find({}, {"days.images": 0})
        .sort("_id", -1)
        .to_list(500)
    )
    is_admin = user.role == "admin"
    return [serialize(p, is_admin=is_admin) for p in items]


@router.get("/{package_id}", response_model=PackageOut)
async def get_package(package_id: str, user: CurrentUser = Depends(get_current_user)):
    p = await packages_collection.find_one({"_id": ObjectId(package_id)})
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return serialize(p, is_admin=user.role == "admin")


@router.post("", response_model=PackageOut, status_code=201)
async def create_package(body: PackageCreate, user: CurrentUser = Depends(get_current_user)):
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    res = await packages_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc, is_admin=user.role == "admin")


@router.put("/{package_id}", response_model=PackageOut)
async def update_package(
    package_id: str, body: PackageUpdate, user: CurrentUser = Depends(get_current_user)
):
    existing = await packages_collection.find_one({"_id": ObjectId(package_id)})
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")

    # Regular package edits never touch the net-profit fields — PackageUpdate
    # has no such fields, so there's nothing here that could accidentally
    # overwrite them.
    update = body.model_dump()
    res = await packages_collection.find_one_and_update(
        {"_id": ObjectId(package_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return serialize(res, is_admin=user.role == "admin")


@router.put("/{package_id}/net-profit", response_model=PackageOut)
async def update_net_profit(
    package_id: str, body: NetProfitUpdate, user: CurrentUser = Depends(get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    res = await packages_collection.find_one_and_update(
        {"_id": ObjectId(package_id)},
        {
            "$set": {
                "adultNetProfit": body.adultNetProfit,
                "childNetProfit": body.childNetProfit,
                "infantNetProfit": body.infantNetProfit,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return serialize(res, is_admin=True)


@router.delete("/{package_id}", status_code=204)
async def delete_package(package_id: str, user: CurrentUser = Depends(get_current_user)):
    query = {"_id": ObjectId(package_id)}
    if user.role != "admin":
        query["createdBy"] = user.id
    res = await packages_collection.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
