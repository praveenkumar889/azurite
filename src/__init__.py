from bson import ObjectId
from pymongo.errors import PyMongoError
from pymongo import MongoClient, UpdateOne
import azure.functions as func
import logging
import os
import json
import hashlib
from typing import List, Dict, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Environment variables - set these in Azure Function App settings or local.settings.json
MONGO_CONN_STR = os.getenv("MONGO_CONN_STR", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "mongo_db_KNK")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "mongo_collection_KNK")

# Create Mongo client once per cold start
mongo_client = MongoClient(MONGO_CONN_STR)
db = mongo_client[MONGO_DB]
collection = db[MONGO_COLLECTION]

# Utility functions for document processing and upsert operations


def deterministic_id_from_text(text: str) -> str:
    """Return a hex sha256 digest to use as deterministic id/_id."""
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    return h.hexdigest()

# Normalize document to ensure it has an _id field


def normalize_doc(doc: Dict[str, Any], filename: str, index: int) -> Dict[str, Any]:
    """
    Ensure document has an _id for upsert.
    Priority:
      1) _id present -> use as-is
      2) id present -> use as _id (and remove original id or keep as separate field)
      3) compute deterministic hash of filename + index + some stable fields
    """
    if "_id" in doc:
        # if it's not an ObjectId, leave it as string (Mongo allows string _id)
        return doc

    if "id" in doc:
        doc["_id"] = doc["id"]
        return doc

    # fallback: deterministic id from filename + index + maybe some content snippet
    snippet = json.dumps(doc, sort_keys=True)[
        :200]  # small content fingerprint
    computed = deterministic_id_from_text(f"{filename}:{index}:{snippet}")
    doc["_id"] = computed
    return doc

# Parse JSON content from blob


def parse_json_content(content: bytes):
    """Parse JSON content and return list of documents."""
    text = content.decode("utf-8")
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # Single object
        return [parsed]
    raise ValueError("JSON root must be an object or an array of objects.")

# Bulk upsert documents into MongoDB


def bulk_upsert_docs(docs: List[Dict[str, Any]]):
    """Perform bulk upsert operations using UpdateOne with upsert=True."""
    operations = []
    for d in docs:
        _id = d.get("_id")
        # Build the filter
        if _id is not None:
            filt = {"_id": _id}
            # Remove _id from update doc to avoid ImmutableField errors
            update_doc = dict(d)
            update_doc.pop("_id", None)
            operations.append(
                UpdateOne(filt, {"$set": update_doc}, upsert=True))
        else:
            # If somehow no _id, insert as-is (but not idempotent)
            operations.append(UpdateOne(d, {"$set": d}, upsert=True))

    if not operations:
        return {"matched": 0, "modified": 0, "upserted": 0}

    result = collection.bulk_write(operations, ordered=False)
    return {
        "matched_count": result.matched_count,
        "modified_count": result.modified_count,
        "upserted_count": len(result.upserted_ids) if hasattr(result, "upserted_ids") else 0
    }

# Azure Function entry point


def main(myblob: func.InputStream):
    logging.info(
        f"Blob trigger function processed blob\nName: {myblob.name}\nSize: {myblob.length} bytes")

    try:
        content = myblob.read()
        docs = parse_json_content(content)
    except Exception as e:
        logging.error("Failed to parse blob JSON: %s", e)
        raise

    # Normalize and assign _id where needed
    normalized = []
    for idx, doc in enumerate(docs):
        try:
            nd = normalize_doc(doc, myblob.name, idx)
            normalized.append(nd)
        except Exception as ex:
            logging.error("Failed to normalize doc index %s: %s", idx, ex)

    try:
        stats = bulk_upsert_docs(normalized)
        logging.info("Mongo upsert stats: %s", stats)
    except PyMongoError as me:
        logging.error("Mongo write failed: %s", me)
        raise
    except Exception as e:
        logging.error("Unexpected error while upserting: %s", e)
        raise
