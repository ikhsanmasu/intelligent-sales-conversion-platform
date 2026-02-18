from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.llm.service import list_llm_options
from app.modules.admin.service import (
    list_configs,
    list_prompts,
    update_configs,
    update_prompt,
)

router = APIRouter(tags=["Admin"], prefix="/v1/admin")


class UpdateConfigsRequest(BaseModel):
    configs: dict[str, dict[str, str]]


class UpdatePromptRequest(BaseModel):
    content: str
    name: str | None = None
    description: str | None = None


@router.get("/configs")
async def get_configs():
    return list_configs()


@router.put("/configs")
async def put_configs(request: UpdateConfigsRequest):
    try:
        update_configs(request.configs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "updated"}


@router.get("/prompts")
async def get_prompts():
    return list_prompts()


@router.get("/llm/options")
async def get_llm_options():
    return list_llm_options()


@router.put("/prompts/{slug}")
async def put_prompt(slug: str, request: UpdatePromptRequest):
    data = {"content": request.content}
    if request.name is not None:
        data["name"] = request.name
    if request.description is not None:
        data["description"] = request.description

    ok = update_prompt(slug, data)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "updated"}
