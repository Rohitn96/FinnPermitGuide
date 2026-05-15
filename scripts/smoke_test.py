"""Quick Pinecone smoke test — run once to verify the vectorstore is live."""
import os
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("USE_PINECONE", "true")

from rag.chain import vectorstore

results = vectorstore.similarity_search_with_relevance_scores(
    "permanent residence requirements Finland", k=1
)
doc, score = results[0]
print(f"Score : {score:.3f}")
print(f"URL   : {doc.metadata.get('source', '')}")
print(f"Text  : {doc.page_content[:120]}...")
print("Pinecone vectorstore OK")
