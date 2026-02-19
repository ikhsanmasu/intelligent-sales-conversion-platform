import json
import time

from sqlmodel import Session, delete, select

from app.core.database import app_engine
from app.modules.chatbot.models import (
    Conversation,
    ConversationHistory,
    ConversationMessage,
)

MAX_CONVERSATIONS = 20


class ChatRepository:
    def __init__(self, engine=app_engine):
        self.engine = engine

    @staticmethod
    def _conversation_to_dict(conv: Conversation) -> dict:
        return {
            "id": conv.id,
            "user_id": conv.user_id,
            "title": conv.title,
            "created_at": float(conv.created_at),
            "updated_at": float(conv.updated_at),
        }

    @staticmethod
    def _history_to_dict(entry: ConversationHistory) -> dict:
        return {
            "id": int(entry.id) if entry.id is not None else 0,
            "user_id": entry.user_id,
            "conversation_id": entry.conversation_id,
            "user_message": entry.user_message,
            "assistant_content": entry.assistant_content,
            "assistant_thinking": entry.assistant_thinking,
            "created_at": float(entry.created_at),
        }

    def create_conversation(self, user_id: str, title: str = "New Chat") -> dict:
        now = time.time()
        conversation = Conversation(
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )

        with Session(self.engine) as session:
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            self._enforce_max_conversations(session, user_id)

            return self._conversation_to_dict(conversation)

    def list_conversations(self, user_id: str) -> list[dict]:
        with Session(self.engine) as session:
            conversations = session.exec(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
            ).all()
            return [self._conversation_to_dict(conv) for conv in conversations]

    @staticmethod
    def _conversation_detail_payload(
        session: Session, conversation: Conversation
    ) -> dict:
        messages = session.exec(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        ).all()

        data = ChatRepository._conversation_to_dict(conversation)
        data["messages"] = []
        for message in messages:
            payload = {
                "role": message.role,
                "content": message.content,
                "created_at": float(message.created_at),
            }
            if message.thinking:
                payload["thinking"] = message.thinking
            if message.role == "assistant" and message.metadata:
                try:
                    payload["metadata"] = json.loads(message.metadata)
                except (json.JSONDecodeError, TypeError):
                    pass
            data["messages"].append(payload)
        return data

    def get_conversation(self, user_id: str, conversation_id: str) -> dict | None:
        with Session(self.engine) as session:
            conversation = session.exec(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .where(Conversation.user_id == user_id)
            ).first()
            if not conversation:
                return None

            return self._conversation_detail_payload(session, conversation)

    def get_conversation_by_id(self, conversation_id: str) -> dict | None:
        with Session(self.engine) as session:
            conversation = session.exec(
                select(Conversation).where(Conversation.id == conversation_id)
            ).first()
            if not conversation:
                return None
            return self._conversation_detail_payload(session, conversation)

    def list_conversations_global(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        with Session(self.engine) as session:
            conversations = session.exec(
                select(Conversation)
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [self._conversation_to_dict(conv) for conv in conversations]

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        with Session(self.engine) as session:
            conversation = session.exec(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .where(Conversation.user_id == user_id)
            ).first()
            if not conversation:
                return False

            session.exec(
                delete(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation_id
                )
            )
            session.exec(
                delete(ConversationHistory).where(
                    ConversationHistory.conversation_id == conversation_id
                )
            )
            session.delete(conversation)
            session.commit()
            return True

    def update_conversation_title(self, user_id: str, conversation_id: str, title: str) -> bool:
        with Session(self.engine) as session:
            conversation = session.exec(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .where(Conversation.user_id == user_id)
            ).first()
            if not conversation:
                return False

            conversation.title = title
            conversation.updated_at = time.time()
            session.add(conversation)
            session.commit()
            return True

    def save_messages(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_content: str,
        assistant_thinking: str | None = None,
        assistant_metadata: dict | None = None,
    ) -> bool:
        with Session(self.engine) as session:
            conversation = session.exec(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .where(Conversation.user_id == user_id)
            ).first()
            if not conversation:
                return False

            now = time.time()
            session.add(
                ConversationMessage(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                    created_at=now,
                )
            )
            session.add(
                ConversationMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content,
                    thinking=assistant_thinking,
                    metadata=json.dumps(assistant_metadata) if assistant_metadata else None,
                    created_at=now,
                )
            )
            session.add(
                ConversationHistory(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_content=assistant_content,
                    assistant_thinking=assistant_thinking,
                    created_at=now,
                )
            )
            conversation.updated_at = now
            session.add(conversation)
            session.commit()
            return True

    def list_history(
        self,
        user_id: str,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with Session(self.engine) as session:
            query = (
                select(ConversationHistory)
                .where(ConversationHistory.user_id == user_id)
                .order_by(ConversationHistory.created_at.desc(), ConversationHistory.id.desc())
                .limit(limit)
            )
            if conversation_id:
                query = query.where(ConversationHistory.conversation_id == conversation_id)

            entries = session.exec(query).all()
            return [self._history_to_dict(entry) for entry in entries]

    def clear_history(self, user_id: str, conversation_id: str | None = None) -> int:
        with Session(self.engine) as session:
            query = select(ConversationHistory.id).where(ConversationHistory.user_id == user_id)
            if conversation_id:
                query = query.where(ConversationHistory.conversation_id == conversation_id)

            ids = session.exec(query).all()
            if not ids:
                return 0

            delete_query = delete(ConversationHistory).where(ConversationHistory.user_id == user_id)
            if conversation_id:
                delete_query = delete_query.where(
                    ConversationHistory.conversation_id == conversation_id
                )
            session.exec(delete_query)
            session.commit()
            return len(ids)

    def _enforce_max_conversations(self, session: Session, user_id: str) -> None:
        conversations = session.exec(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        ).all()

        if len(conversations) <= MAX_CONVERSATIONS:
            return

        stale_conversations = conversations[MAX_CONVERSATIONS:]
        stale_ids = [conv.id for conv in stale_conversations]

        session.exec(
            delete(ConversationMessage).where(
                ConversationMessage.conversation_id.in_(stale_ids)
            )
        )
        session.exec(
            delete(ConversationHistory).where(
                ConversationHistory.conversation_id.in_(stale_ids)
            )
        )
        for conversation in stale_conversations:
            session.delete(conversation)

        session.commit()
