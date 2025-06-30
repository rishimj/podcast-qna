#!/usr/bin/env python3
"""
rag_sed_fast.py

A speed-optimized RAG QA agent over your SED transcripts, using
a lightweight 3B GGUF model (e.g. Dolly v2-3B) with llama-cpp-python.
"""

import os
import glob
import argparse
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.llms import LlamaCpp
from langchain.chains import RetrievalQA
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

def load_transcripts(folder: str):
    docs = []
    for path in glob.glob(os.path.join(folder, "*.txt")):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        docs.append(Document(page_content=text, metadata={"source": os.path.basename(path)}))
    return docs

def build_vectorstore(docs):
    # smaller chunks for faster retrieval
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return FAISS.from_documents(chunks, embeddings)

def init_fast_llm(model_path: str, n_ctx: int, max_tokens: int, threads: int):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    print(f"Loading model ({model_path}) …")
    return LlamaCpp(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=threads,
        temperature=0.1,
        max_tokens=max_tokens,
        streaming=True,
        callbacks=[StreamingStdOutCallbackHandler()],
        verbose=False,
    )

def init_qa(llm, index, k: int):
    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=index.as_retriever(search_kwargs={"k": k}),
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-path",
        default=os.path.expanduser("~/Downloads/dolly-v2-3b-instruct.Q4_K_M.gguf"),
        help="3B GGUF model file (e.g. Dolly v2-3B)",
    )
    parser.add_argument(
        "--transcript-dir",
        default="transcripts",
        help="Folder of your .txt transcripts",
    )
    parser.add_argument(
        "--k", type=int, default=2,
        help="How many chunks to retrieve (smaller → faster)",
    )
    parser.add_argument(
        "--n-ctx", type=int, default=1024,
        help="Context window size (smaller → faster)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=128,
        help="Max tokens to generate per query",
    )
    parser.add_argument(
        "--threads", type=int, default=os.cpu_count(),
        help="CPU threads for inference",
    )
    args = parser.parse_args()

    print("🔖 Loading transcripts…")
    docs = load_transcripts(args.transcript_dir)
    if not docs:
        print("❌ No transcripts found in", args.transcript_dir)
        return

    print("📚 Building vector store…")
    index = build_vectorstore(docs)

    print("🤖 Initializing fast LLM…")
    llm = init_fast_llm(
        model_path=args.model_path,
        n_ctx=args.n_ctx,
        max_tokens=args.max_tokens,
        threads=args.threads,
    )

    print("🔍 Creating RetrievalQA chain…")
    qa = init_qa(llm, index, args.k)

    print("\n✅ Ready! (type exit to quit)")
    while True:
        q = input("\nQuestion> ").strip()
        if q.lower() in ("exit", "quit"):
            break
        print("🤔 Thinking…")
        qa.invoke({"query": q})
        print()  # newline after stream

if __name__ == "__main__":
    main()
