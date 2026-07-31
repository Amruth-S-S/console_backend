from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import packages_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import PackageCreate, PackageOut, PackageUpdate

router = APIRouter(prefix="/packages", tags=["packages"])


def serialize(p: dict) -> PackageOut:
    return PackageOut(
        id=str(p["_id"]),
        createdAt=p["createdAt"],
        companyName=p.get("companyName", ""),
        logo=p.get("logo"),
        poster=p.get("poster"),
        packageTitle=p.get("packageTitle", ""),
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
    )


@router.get("", response_model=list[PackageOut])
async def list_packages(user: CurrentUser = Depends(get_current_user)):
    query = {} if user.role == "admin" else {"createdBy": user.id}
    items = await packages_collection.find(query).sort("_id", -1).to_list(500)
    return [serialize(p) for p in items]


@router.get("/{package_id}", response_model=PackageOut)
async def get_package(package_id: str, user: CurrentUser = Depends(get_current_user)):
    p = await packages_collection.find_one({"_id": ObjectId(package_id)})
    if not p or (user.role != "admin" and p.get("createdBy") != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return serialize(p)


@router.post("", response_model=PackageOut, status_code=201)
async def create_package(body: PackageCreate, user: CurrentUser = Depends(get_current_user)):
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    res = await packages_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{package_id}", response_model=PackageOut)
async def update_package(
    package_id: str, body: PackageUpdate, user: CurrentUser = Depends(get_current_user)
):
    existing = await packages_collection.find_one({"_id": ObjectId(package_id)})
    if not existing or (user.role != "admin" and existing.get("createdBy") != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")

    update = body.model_dump()
    res = await packages_collection.find_one_and_update(
        {"_id": ObjectId(package_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return serialize(res)


@router.delete("/{package_id}", status_code=204)
async def delete_package(package_id: str, user: CurrentUser = Depends(get_current_user)):
    query = {"_id": ObjectId(package_id)}
    if user.role != "admin":
        query["createdBy"] = user.id
    res = await packages_collection.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
