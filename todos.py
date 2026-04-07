import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc

from database import get_db
import models, schemas
from auth_utils import get_current_user
from integrations import cache_get, cache_set, cache_delete_pattern, publish_event

router = APIRouter()

PUBLIC_CACHE_TTL = 60  # seconds


def todo_to_response(todo: models.TodoItem) -> schemas.TodoResponse:
    return schemas.TodoResponse(
        id=str(todo.id),
        title=todo.title,
        details=todo.details,
        priority=todo.priority.value if hasattr(todo.priority, "value") else todo.priority,
        dueDate=todo.due_date,
        isCompleted=todo.is_completed,
        isPublic=todo.is_public,
        createdAt=todo.created_at.isoformat() + "Z" if todo.created_at else None,
        updatedAt=todo.updated_at.isoformat() + "Z" if todo.updated_at else None,
    )


def apply_filters_and_sort(query, model, status_filter, priority, due_from, due_to, sort_by, sort_dir, search):
    if status_filter == "active":
        query = query.filter(model.is_completed == False)
    elif status_filter == "completed":
        query = query.filter(model.is_completed == True)

    if priority:
        query = query.filter(model.priority == priority)

    if due_from:
        query = query.filter(model.due_date >= due_from)
    if due_to:
        query = query.filter(model.due_date <= due_to)

    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(model.title.ilike(pattern), model.details.ilike(pattern)))

    sort_col_map = {
        "createdAt": model.created_at,
        "dueDate": model.due_date,
        "priority": model.priority,
        "title": model.title,
    }
    col = sort_col_map.get(sort_by, model.created_at)
    query = query.order_by(asc(col) if sort_dir == "asc" else desc(col))

    return query


def paginate(query, page, page_size):
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return items, total, total_pages


def _invalidate_public_cache():
    """Delete all cached public todo pages when data changes."""
    cache_delete_pattern("public_todos:*")


# ─── Public endpoint ──────────────────────────────────────────────────────────

@router.get("/public", response_model=schemas.PaginatedTodoResponse)
def list_public_todos(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=50),
    status: Optional[str] = Query("all"),
    priority: Optional[str] = Query(None),
    dueFrom: Optional[str] = Query(None),
    dueTo: Optional[str] = Query(None),
    sortBy: str = Query("createdAt"),
    sortDir: str = Query("desc"),
    search: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    # Build a cache key from all query params
    cache_key = (
        f"public_todos:p{page}:ps{pageSize}:st{status}:pr{priority}"
        f":df{dueFrom}:dt{dueTo}:sb{sortBy}:sd{sortDir}:s{search}"
    )
    cached = cache_get(cache_key)
    if cached:
        return schemas.PaginatedTodoResponse(**cached)

    query = db.query(models.TodoItem).filter(models.TodoItem.is_public == True)
    query = apply_filters_and_sort(query, models.TodoItem, status, priority, dueFrom, dueTo, sortBy, sortDir, search)
    items, total, total_pages = paginate(query, page, pageSize)

    result = schemas.PaginatedTodoResponse(
        items=[todo_to_response(t) for t in items],
        page=page,
        pageSize=pageSize,
        totalItems=total,
        totalPages=total_pages,
    )
    cache_set(cache_key, result.model_dump(), ttl=PUBLIC_CACHE_TTL)
    return result


# ─── Authenticated endpoints ──────────────────────────────────────────────────

@router.get("", response_model=schemas.PaginatedTodoResponse)
def list_todos(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=50),
    status: Optional[str] = Query("all"),
    priority: Optional[str] = Query(None),
    dueFrom: Optional[str] = Query(None),
    dueTo: Optional[str] = Query(None),
    sortBy: str = Query("createdAt"),
    sortDir: str = Query("desc"),
    search: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.TodoItem).filter(models.TodoItem.user_id == current_user.id)
    query = apply_filters_and_sort(query, models.TodoItem, status, priority, dueFrom, dueTo, sortBy, sortDir, search)
    items, total, total_pages = paginate(query, page, pageSize)
    return schemas.PaginatedTodoResponse(
        items=[todo_to_response(t) for t in items],
        page=page,
        pageSize=pageSize,
        totalItems=total,
        totalPages=total_pages,
    )


@router.post("", response_model=schemas.TodoResponse, status_code=201)
def create_todo(
    body: schemas.CreateTodoRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    todo = models.TodoItem(
        user_id=current_user.id,
        title=body.title,
        details=body.details,
        priority=body.priority.value,
        due_date=body.dueDate,
        is_public=body.isPublic,
        is_completed=False,
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    response.headers["Location"] = f"/api/todos/{todo.id}"

    result = todo_to_response(todo)

    # Publish event + invalidate cache if public
    publish_event("TodoCreated", result.model_dump())
    if todo.is_public:
        _invalidate_public_cache()

    return result


@router.get("/{todo_id}", response_model=schemas.TodoResponse)
def get_todo(
    todo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    todo = db.query(models.TodoItem).filter(models.TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    if str(todo.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return todo_to_response(todo)


@router.put("/{todo_id}", response_model=schemas.TodoResponse)
def update_todo(
    todo_id: str,
    body: schemas.UpdateTodoRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    todo = db.query(models.TodoItem).filter(models.TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    if str(todo.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    was_public = todo.is_public
    todo.title = body.title
    todo.details = body.details
    todo.priority = body.priority.value
    todo.due_date = body.dueDate
    todo.is_public = body.isPublic
    todo.is_completed = body.isCompleted
    todo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(todo)

    result = todo_to_response(todo)
    publish_event("TodoUpdated", result.model_dump())
    if was_public or todo.is_public:
        _invalidate_public_cache()

    return result


@router.patch("/{todo_id}/completion", response_model=schemas.TodoResponse)
def set_completion(
    todo_id: str,
    body: schemas.SetCompletionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    todo = db.query(models.TodoItem).filter(models.TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    if str(todo.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    todo.is_completed = body.isCompleted
    todo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(todo)

    result = todo_to_response(todo)
    publish_event("TodoCompleted" if body.isCompleted else "TodoUncompleted", result.model_dump())
    if todo.is_public:
        _invalidate_public_cache()

    return result


@router.delete("/{todo_id}", status_code=204)
def delete_todo(
    todo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    todo = db.query(models.TodoItem).filter(models.TodoItem.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    if str(todo.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    was_public = todo.is_public
    todo_id_str = str(todo.id)
    db.delete(todo)
    db.commit()

    publish_event("TodoDeleted", {"id": todo_id_str})
    if was_public:
        _invalidate_public_cache()

    return Response(status_code=204)
