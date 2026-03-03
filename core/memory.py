import os
import logging
import time
from typing import List
from config import config

# Storage path for ChromaDB
DB_DIR = os.path.join(os.getcwd(), "chroma_db")

_embeddings = None

def get_embeddings():
    """Lazy loader for embeddings to avoid startup delay."""
    from langchain_huggingface import HuggingFaceEmbeddings
    global _embeddings
    if _embeddings is None:
        logging.info("⏳ Loading embedding model (all-MiniLM-L6-v2) on demand...")
        start_emb = time.time()
        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        logging.info(f"✅ Embedding model loaded in {time.time() - start_emb:.2f}s")
    return _embeddings

def get_vector_db():
    """Initializes or loads the existing vector database."""
    from langchain_chroma import Chroma
    return Chroma(
        persist_directory=DB_DIR,
        embedding_function=get_embeddings(),
        collection_name="obsidian_knowledge"
    )

def index_knowledge_base():
    """
    Manually scans paths for MD, PDF, and DOCX files.
    """
    from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    
    paths = [config.obsidian_vault_path, config.job_search_path]
    all_docs = []

    for base_path in paths:
        if not base_path or not os.path.exists(base_path):
            logging.warning(f"Path not found: {base_path}")
            continue
            
        source_type = "obsidian" if "Obsidian" in base_path else "job_search"
        logging.info(f"Scanning {source_type} directory: {base_path}")
        
        for root, dirs, files in os.walk(base_path):
            for file in files:
                file_path = os.path.join(root, file)
                ext = file.lower().split('.')[-1]
                
                try:
                    loader = None
                    if ext == 'md':
                        loader = TextLoader(file_path, encoding='utf-8')
                    elif ext == 'pdf':
                        loader = PyPDFLoader(file_path)
                    elif ext == 'docx':
                        loader = Docx2txtLoader(file_path)
                    
                    if loader:
                        docs = loader.load()
                        for i, doc in enumerate(docs):
                            filename = os.path.basename(file_path)
                            doc.page_content = f"ИСТОЧНИК: {source_type.upper()}\nФАЙЛ: {filename}\n---\n{doc.page_content}"
                            # Add source_type to metadata for filtering
                            doc.metadata["source_type"] = source_type
                            all_docs.append(doc)
                        logging.info(f"  [OK] {filename} ({source_type})")
                except Exception as e:
                    logging.error(f"  [!] Ошибка в {file}: {e}")

    if not all_docs:
        logging.warning("No documents found to index.")
        return False

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    # Refresh DB
    if os.path.exists(DB_DIR):
        import shutil
        try:
            shutil.rmtree(DB_DIR)
            logging.info("🗑️ Old knowledge base cleared.")
        except Exception as e:
            logging.error(f"Could not clear old DB: {e}")

    Chroma.from_documents(
        documents=splits,
        embedding=get_embeddings(),
        persist_directory=DB_DIR,
        collection_name="obsidian_knowledge"
    )
    
    logging.info(f"Successfully indexed {len(all_docs)} files into {len(splits)} chunks.")
    return True

def query_knowledge(query: str, k: int = 3, source_type: str = None):
    """
    Searches the vector database. Optional filtering by source_type ('obsidian' or 'job_search').
    """
    try:
        start_q = time.time()
        db = get_vector_db()
        
        filter_dict = {"source_type": source_type} if source_type else None
        
        results = db.similarity_search(query, k=k, filter=filter_dict)
        logging.info(f"🔎 Search ({source_type or 'all'}): found {len(results)} docs in {time.time() - start_q:.2f}s")
        return results
    except Exception as e:
        logging.error(f"Error querying knowledge: {e}")
        return []
