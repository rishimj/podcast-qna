#!/usr/bin/env python3
"""
rag_sed_ultrafast.py

Speed-optimized RAG QA over your Software Engineering Daily transcripts using
GPT4All model with llama-cpp-python and Sentence-Transformers embeddings.
"""

import os
import glob
import argparse

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings  # Updated import
from langchain_community.vectorstores import FAISS
from langchain_community.llms import GPT4All  # Updated import
from langchain.chains import RetrievalQA
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

def load_transcripts(folder: str):
    """Load all .txt transcripts in a folder into LangChain Documents."""
    docs = []
    for fn in glob.glob(os.path.join(folder, "*.txt")):
        with open(fn, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        docs.append(Document(page_content=text, metadata={"source": os.path.basename(fn)}))
    return docs

def build_index(docs):
    """Split docs into chunks, embed locally, and build a FAISS index."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return FAISS.from_documents(chunks, embeddings)

def init_llm(model_path: str, n_ctx: int, threads: int, max_tokens: int):
    """Initialize the GPT4All quantized LLM for fast CPU inference."""
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"No model found at {model_path}")
    
    # Try with minimal parameters first
    try:
        return GPT4All(
            model=model_path,
            max_tokens=max_tokens,
            n_threads=threads,
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            # Try passing extra parameters through model_kwargs
            model_kwargs={
                "n_ctx": n_ctx,
                "temperature": 0.0,
            }
        )
    except Exception as e:
        print(f"Note: Could not set all model parameters: {e}")
        # Fallback to minimal configuration
        return GPT4All(
            model=model_path,
            max_tokens=max_tokens,
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
        )

def main():
    parser = argparse.ArgumentParser(description="Ultra-fast RAG with GPT4All + FAISS")
    parser.add_argument(
        "--model-path",
        default=os.path.expanduser("~/Downloads/gpt4all-falcon-newbpe-q4_0.gguf"),
        help="Path to your GPT4All model (.gguf)",
    )
    parser.add_argument(
        "--transcript-dir",
        default="transcripts",
        help="Directory containing your .txt transcripts",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=1,
        help="Number of chunks to retrieve per query (1→fastest)",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=512,
        help="Context window size for the model",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=64,
        help="Maximum tokens to generate per query",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=os.cpu_count(),
        help="Number of CPU threads for inference",
    )
    args = parser.parse_args()

    print("🔖 Loading transcripts…")
    docs = load_transcripts(args.transcript_dir)
    if not docs:
        print(f"❌ No transcripts found in '{args.transcript_dir}'")
        return

    print("📚 Building FAISS index…")
    index = build_index(docs)

    print("🤖 Loading GPT4All model…")
    llm = init_llm(
        model_path=args.model_path,
        n_ctx=args.n_ctx,
        threads=args.threads,
        max_tokens=args.max_tokens,
    )

    print(f"🔍 Setting up RetrievalQA (k={args.k})…")
    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=index.as_retriever(search_kwargs={"k": args.k}),
    )

    print("\n✅ Ready! Type your question (or 'exit' to quit).")
    while True:
        query = input("\nQuestion> ").strip()
        if query.lower() in ("exit", "quit"):
            break
        print("🤔 Thinking…")
        try:
            qa.invoke({"query": query})
        except Exception as e:
            print(f"\n❌ Error: {e}")
        print()  # newline after streamed tokens

if __name__ == "__main__":
    main()