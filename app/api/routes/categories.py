from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.core.categories import CATEGORIES, CATEGORY_COLORS, SHEET_GROUPS, SHEET_FALLBACK_GROUP
from app.core.dependencies import get_current_user
from app.services import categories as service
from app.services.settings import get_settings, ROLE_KEYS

router = APIRouter()


class CategoryFields(BaseModel):
    color: str
    sheet_group: str

    @field_validator("color")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class CategoryCreate(CategoryFields):
    name: str

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())


@router.get("/api/categories")
def list_categories(user: dict = Depends(get_current_user)):
    return service.categories_for(user["id"])


@router.get("/api/categories/manage")
def categories_page_data(user: dict = Depends(get_current_user)):
    """Everything the Categories page shows: built-in and own categories with how much uses them."""
    custom = service.list_custom(user["id"])
    names = service.categories_for(user["id"], custom)
    used = service.usage(user["id"], names)
    group_of = {c: g["name"] for g in SHEET_GROUPS for c in g["categories"]}
    # Income, investment and ignored categories aren't spending, so no sheet group applies.
    settings = get_settings(user["id"])
    not_spending = {c for key in ROLE_KEYS for c in settings[key]}
    built_in = [
        {"name": c, "color": CATEGORY_COLORS[c], **used[c],
         "sheet_group": None if c in not_spending else group_of.get(c, SHEET_FALLBACK_GROUP)}
        for c in CATEGORIES
    ]
    return {
        "built_in": built_in,
        "custom": [{**c, **used[c["name"]]} for c in custom],
        "sheet_groups": service.sheet_group_names(),
        "suggested_color": service.suggest_color(user["id"]),
        "max_name_length": service.MAX_NAME_LENGTH,
    }


@router.post("/api/categories")
def create_category(payload: CategoryCreate, user: dict = Depends(get_current_user)):
    problem = (service.name_problem(user["id"], payload.name)
               or service.field_problem(payload.color, payload.sheet_group))
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    return service.add_category(user["id"], payload.name, payload.color, payload.sheet_group)


@router.patch("/api/categories/{category_id}")
def edit_category(category_id: int, payload: CategoryFields, user: dict = Depends(get_current_user)):
    problem = service.field_problem(payload.color, payload.sheet_group)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if not service.update_category(user["id"], category_id, payload.color, payload.sheet_group):
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "updated"}


@router.delete("/api/categories/{category_id}")
def remove_category(category_id: int, user: dict = Depends(get_current_user)):
    problem = service.delete_category(user["id"], category_id)
    if problem == "not found":
        raise HTTPException(status_code=404, detail="Category not found")
    if problem:
        raise HTTPException(status_code=409, detail=problem)
    return {"status": "deleted"}
