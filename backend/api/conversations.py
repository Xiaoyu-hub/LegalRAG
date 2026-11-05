"""会话接口：历史对话的增删查。

和 /chat 的分工：
- `/chat` 负责「问一次并流式返回答案」，写库在流结束后由它自己完成；
- 这里只负责读与整理（列表、详情、改名、删除）。

这样拆的原因：流式响应一开始就要把 header 发出去，没法再把「本轮会话 id」当
响应体返回；前端必须能先建会话再提问，所以建会话必须是独立端点。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.deps import resolve_tenant
from backend.storage.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str = ""
    document_id: int | None = None


class RenameConversationRequest(BaseModel):
    title: str


def get_store(request: Request) -> ConversationStore:
    """取会话库单例。

    懒创建：单测里只挂路由、不跑 startup 时也能用；生产它已经在 startup 建好了。
    """
    store = getattr(request.app.state, "conversation_store", None)
    if store is None:
        store = ConversationStore()
        request.app.state.conversation_store = store
    return store


def _ok(data) -> dict:
    return {"status": "ok", "data": data, "error": None}


@router.post("")
async def create_conversation(req: CreateConversationRequest, request: Request,
                             tenant: str = Depends(resolve_tenant)):
    store = get_store(request)
    conv_id = store.create(tenant=tenant, title=req.title, document_id=req.document_id)
    return _ok(store.get(conv_id, tenant=tenant))


@router.get("")
async def list_conversations(request: Request, tenant: str = Depends(resolve_tenant),
                             limit: int = 50):
    store = get_store(request)
    if limit > 200:
        limit = 200
    return _ok({"conversations": store.list_conversations(tenant=tenant, limit=limit)})


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: int, request: Request,
                           tenant: str = Depends(resolve_tenant)):
    store = get_store(request)
    conv = store.get(conversation_id, tenant=tenant)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    conv["messages"] = store.messages(conversation_id)
    return _ok(conv)


@router.patch("/{conversation_id}")
async def rename_conversation(conversation_id: int, req: RenameConversationRequest,
                              request: Request, tenant: str = Depends(resolve_tenant)):
    store = get_store(request)
    if not store.rename(conversation_id, req.title, tenant=tenant):
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return _ok(store.get(conversation_id, tenant=tenant))


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: int, request: Request,
                              tenant: str = Depends(resolve_tenant)):
    store = get_store(request)
    if not store.delete(conversation_id, tenant=tenant):
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return _ok({"deleted": conversation_id})
