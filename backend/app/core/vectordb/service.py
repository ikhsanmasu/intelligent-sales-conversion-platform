from typing import Dict, Tuple

from app.core.config import settings
from app.core.vectordb.base import BaseVectorDB
from app.core.vectordb.providers.chroma import ChromaVectorDB
from app.core.vectordb.providers.memory import MemoryVectorDB
from app.core.vectordb.providers.milvus import MilvusVectorDB
from app.core.vectordb.providers.pinecone import PineconeVectorDB
from app.core.vectordb.providers.qdrant import QdrantVectorDB

PROVIDER_ALIASES = {
    "in_memory": "memory",
}

VECTORDB_REGISTRY = {
    "memory": MemoryVectorDB,
    "qdrant": QdrantVectorDB,
    "pinecone": PineconeVectorDB,
    "chroma": ChromaVectorDB,
    "milvus": MilvusVectorDB,
}

PROVIDER_CONFIG: Dict[str, dict[str, str]] = {
    "memory": {},
    "qdrant": {
        "url_attr": "VECTORDB_URL",
        "api_key_attr": "VECTORDB_API_KEY",
        "collection_attr": "VECTORDB_COLLECTION",
    },
    "pinecone": {
        "api_key_attr": "VECTORDB_API_KEY",
        "index_attr": "VECTORDB_INDEX",
        "namespace_attr": "VECTORDB_NAMESPACE",
    },
    "chroma": {
        "url_attr": "VECTORDB_URL",
        "collection_attr": "VECTORDB_COLLECTION",
    },
    "milvus": {
        "url_attr": "VECTORDB_URL",
        "collection_attr": "VECTORDB_COLLECTION",
    },
}


# cache instance per (provider, url, index, collection, namespace)
_instances: Dict[Tuple[str, str, str, str, str], BaseVectorDB] = {}


def list_vectordb_options() -> dict[str, object]:
    providers = list(VECTORDB_REGISTRY.keys())
    return {"providers": providers}


def _resolve(group: str, key: str, fallback_attr: str) -> str:
    try:
        from app.modules.admin.service import resolve_config
        val = resolve_config(group, key)
        if val:
            return val
    except Exception:
        pass
    return str(getattr(settings, fallback_attr, ""))


def _resolve_api_key(provider: str) -> str:
    provider = PROVIDER_ALIASES.get(provider, provider)
    cfg = PROVIDER_CONFIG.get(provider, {})
    attr = cfg.get("api_key_attr", "")
    if attr:
        val = getattr(settings, attr, "")
        if val:
            return str(val)
    return ""



def create_vectordb(
    provider: str | None = None,
    url: str | None = None,
    api_key: str | None = None,
    collection: str | None = None,
    index: str | None = None,
    namespace: str | None = None,
    config_group: str = "vectordb",
    use_cache: bool = True,
) -> BaseVectorDB:
    provider = provider or _resolve(config_group, "provider", "VECTORDB_PROVIDER")
    provider = PROVIDER_ALIASES.get(provider, provider)

    if provider not in VECTORDB_REGISTRY:
        raise ValueError(f"Unsupported vector DB provider: {provider}")

    cfg = PROVIDER_CONFIG.get(provider, {})
    url = url or _resolve(config_group, "url", cfg.get("url_attr", "VECTORDB_URL"))
    collection = collection or _resolve(
        config_group, "collection", cfg.get("collection_attr", "VECTORDB_COLLECTION")
    )
    index = index or _resolve(config_group, "index", cfg.get("index_attr", "VECTORDB_INDEX"))
    namespace = namespace or _resolve(
        config_group, "namespace", cfg.get("namespace_attr", "VECTORDB_NAMESPACE")
    )
    api_key = api_key or _resolve_api_key(provider)

    cache_key = (provider, url or "", index or "", collection or "", namespace or "")
    if use_cache and cache_key in _instances:
        return _instances[cache_key]

    if provider == "memory":
        instance = MemoryVectorDB(collection=collection)
    elif provider == "qdrant":
        if not url:
            raise ValueError("VECTORDB_URL is required for Qdrant provider.")
        instance = QdrantVectorDB(url=url, api_key=api_key or None, collection=collection)
    elif provider == "pinecone":
        if not api_key:
            raise ValueError("VECTORDB_API_KEY is required for Pinecone provider.")
        if not index:
            raise ValueError("VECTORDB_INDEX is required for Pinecone provider.")
        instance = PineconeVectorDB(api_key=api_key, index=index, namespace=namespace or None)
    elif provider == "chroma":
        instance = ChromaVectorDB(url=url or None, collection=collection)
    elif provider == "milvus":
        if not url:
            raise ValueError("VECTORDB_URL is required for Milvus provider.")
        if not collection:
            raise ValueError("VECTORDB_COLLECTION is required for Milvus provider.")
        instance = MilvusVectorDB(url=url, collection=collection)
    else:
        raise ValueError(f"Unsupported vector DB provider: {provider}")

    if use_cache:
        _instances[cache_key] = instance

    return instance


def clear_vectordb_cache() -> None:
    _instances.clear()
