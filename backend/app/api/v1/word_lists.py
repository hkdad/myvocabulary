from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_learner, require_parent
from app.database import get_db
from app.models.user import User
from app.schemas.word_list import (
    AssignedListsResponse,
    AssignmentResponse,
    AssignmentsResponse,
    CatalogResponse,
    WordListAssignRequest,
    WordListCreateRequest,
    WordListDetailResponse,
    WordListItemCreateRequest,
    WordListItemResponse,
    WordListSummary,
    WordListUpdateRequest,
)
from app.services import word_list_service

router = APIRouter(prefix="/word-lists", tags=["word-lists"])


@router.get("/catalog", response_model=CatalogResponse)
async def browse_catalog(
    level: str | None = Query(default=None, max_length=8),
    _parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> CatalogResponse:
    lists = await word_list_service.list_catalog(db, level)
    return CatalogResponse(level=level, lists=[WordListSummary(**item) for item in lists])


@router.get("/assigned", response_model=AssignedListsResponse)
async def list_assigned_word_lists(
    user: User = Depends(require_learner),
    db: AsyncSession = Depends(get_db),
) -> AssignedListsResponse:
    if user.learner_profile is None:
        return AssignedListsResponse(lists=[])
    lists = await word_list_service.list_assigned_for_learner(db, user.learner_profile.id)
    return AssignedListsResponse(lists=lists)


@router.get("", response_model=list[WordListSummary])
async def list_word_lists(
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> list[WordListSummary]:
    lists = await word_list_service.list_parent_word_lists(db, parent.id)
    return [WordListSummary(**item) for item in lists]


@router.post("", response_model=WordListDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_word_list(
    payload: WordListCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    if user.role == "parent":
        word_list = await word_list_service.create_word_list(
            db,
            parent_id=user.id,
            name=payload.name,
            description=payload.description,
            level_tag=payload.level_tag,
        )
        detail = await word_list_service.get_word_list_detail_for_parent(db, word_list.id, user.id)
        return WordListDetailResponse(**detail)

    if user.role == "learner":
        if user.learner_profile is None or user.parent_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Learner profile required"},
            )
        word_list = await word_list_service.create_learner_word_list(
            db,
            learner_id=user.learner_profile.id,
            parent_id=user.parent_id,
            name=payload.name,
            description=payload.description,
            level_tag=payload.level_tag,
        )
        detail = await word_list_service.get_word_list_detail_for_learner(
            db, word_list.id, user.learner_profile.id
        )
        return WordListDetailResponse(**detail)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "FORBIDDEN", "message": "Not allowed to create word lists"},
    )


@router.get("/{list_id}", response_model=WordListDetailResponse)
async def get_word_list(
    list_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    if user.role == "parent":
        detail = await word_list_service.get_word_list_detail_for_parent(db, list_id, user.id)
    else:
        if user.learner_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")
        detail = await word_list_service.get_word_list_detail_for_learner(
            db, list_id, user.learner_profile.id
        )
    return WordListDetailResponse(**detail)


@router.patch("/{list_id}", response_model=WordListDetailResponse)
async def update_word_list(
    list_id: int,
    payload: WordListUpdateRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    word_list = await word_list_service.get_parent_word_list(db, list_id, parent.id)
    await word_list_service.update_word_list(
        db,
        word_list,
        name=payload.name,
        description=payload.description,
        level_tag=payload.level_tag,
        is_active=payload.is_active,
    )
    detail = await word_list_service.get_word_list_detail_for_parent(db, list_id, parent.id)
    return WordListDetailResponse(**detail)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word_list(
    list_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.role == "parent":
        word_list = await word_list_service.get_parent_word_list(db, list_id, user.id)
    elif user.role == "learner" and user.learner_profile is not None:
        word_list = await word_list_service.get_learner_owned_word_list(
            db, list_id, user.learner_profile.id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Not allowed to delete this list"},
        )
    await word_list_service.delete_word_list(db, word_list)


@router.post(
    "/{list_id}/items", response_model=WordListItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_word_list_item(
    list_id: int,
    payload: WordListItemCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListItemResponse:
    if user.role == "parent":
        word_list = await word_list_service.get_parent_word_list(db, list_id, user.id)
    elif user.role == "learner" and user.learner_profile is not None:
        word_list = await word_list_service.get_learner_owned_word_list(
            db, list_id, user.learner_profile.id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Not allowed to edit this list"},
        )

    item = await word_list_service.add_word_to_list(
        db,
        word_list,
        word=payload.word,
        notes=payload.notes,
        sort_order=payload.sort_order,
    )
    return WordListItemResponse(
        id=item.id,
        sort_order=item.sort_order,
        notes=item.notes,
        dictionary_entry=word_list_service.entry_summary(item.dictionary_entry),
    )


@router.delete("/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_word_list_item(
    list_id: int,
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.role == "parent":
        word_list = await word_list_service.get_parent_word_list(db, list_id, user.id)
    elif user.role == "learner" and user.learner_profile is not None:
        word_list = await word_list_service.get_learner_owned_word_list(
            db, list_id, user.learner_profile.id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Not allowed to edit this list"},
        )
    await word_list_service.remove_word_from_list(db, word_list, item_id)


@router.post(
    "/{list_id}/assign", response_model=AssignmentsResponse, status_code=status.HTTP_201_CREATED
)
async def assign_word_list(
    list_id: int,
    payload: WordListAssignRequest,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> AssignmentsResponse:
    word_list = await word_list_service.get_parent_word_list(db, list_id, parent.id)
    assignments = await word_list_service.assign_word_list(
        db,
        word_list,
        parent_id=parent.id,
        learner_ids=payload.learner_ids,
        due_date=payload.due_date,
    )
    return AssignmentsResponse(
        assignments=[
            AssignmentResponse(
                id=assignment.id,
                word_list_id=assignment.word_list_id,
                learner_id=assignment.learner_id,
                assigned_at=assignment.assigned_at,
                due_date=assignment.due_date,
                is_active=assignment.is_active,
            )
            for assignment in assignments
        ]
    )


@router.delete("/{list_id}/assign/{learner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_word_list(
    list_id: int,
    learner_id: int,
    parent: User = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
) -> None:
    word_list = await word_list_service.get_parent_word_list(db, list_id, parent.id)
    await word_list_service.unassign_word_list(db, word_list, learner_id, parent.id)
