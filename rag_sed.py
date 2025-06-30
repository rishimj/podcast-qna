#!/usr/bin/env python3
"""
rag_sed_llamacpp.py

Build a RAG-powered QA agent over your Software Engineering Daily transcripts
using a local GGUF model via llama-cpp-python and Sentence-Transformers embeddings.
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

# --- Step 1: Load transcripts from disk ---
def load_transcripts(folder: str):
    docs = []
    for path in glob.glob(os.path.join(folder, "*.txt")):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        docs.append(Document(page_content=text, metadata={"source": os.path.basename(path)}))
    return docs

# --- Step 2–4: Chunk, embed, and index ---
def build_vectorstore(
    docs,
    embedding_model_name="all-MiniLM-L6-v2",
    chunk_size=1000,
    chunk_overlap=200,
):
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
    return FAISS.from_documents(chunks, embeddings)

# --- Step 5: Initialize local LlamaCpp model ---
def init_llamacpp_llm(model_path: str, n_ctx: int = 2048):
    """Initialize LlamaCpp with the downloaded GGUF model."""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found at: {model_path}")
    
    print(f"Loading model from: {model_path} (this may take a moment)...")
    
    llm = LlamaCpp(
        model_path=model_path,
        n_ctx=n_ctx,                # Context window size
        n_threads=8,                # Adjust based on your CPU cores
        temperature=0.1,
        max_tokens=512,
        streaming=True,             # Enable streaming output
        callbacks=[StreamingStdOutCallbackHandler()],
        verbose=False,
    )
    return llm

# --- Step 6: Create a RetrievalQA chain ---
def init_qa_chain(llm, vector_index, k: int = 4):
    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_index.as_retriever(search_kwargs={"k": k}),
    )

# --- Main: parse args, build everything, launch REPL ---
def main():
    parser = argparse.ArgumentParser(
        description="RAG over SED transcripts using local GGUF model + FAISS"
    )
    parser.add_argument(
        "--model-path",
        default=os.path.expanduser("~/Downloads/mistral-7b-instruct-v0.1.Q4_K_M.gguf"),
        help="Path to the GGUF model file",
    )
    parser.add_argument(
        "--transcript-dir",
        default="transcripts",
        help="Folder where your .txt transcripts live",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=4,
        help="How many chunks to retrieve per query",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=2048,
        help="Context window size for the model",
    )
    args = parser.parse_args()

    print("🔖 Loading transcripts…")
    documents = load_transcripts(args.transcript_dir)
    if not documents:
        print(f"❌ No .txt files found in {args.transcript_dir}")
        return

    print("📚 Building vector store…")
    vector_index = build_vectorstore(documents)

    print(f"🤖 Initializing local GGUF model ({args.model_path})…")
    try:
        llm = init_llamacpp_llm(args.model_path, n_ctx=args.n_ctx)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n💡 To download a model, run:")
        print("  curl -L -o ~/Downloads/mistral-7b-instruct-v0.1.Q4_K_M.gguf \\")
        print('    "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf"')
        return

    print("🔍 Setting up RetrievalQA chain…")
    qa = init_qa_chain(llm, vector_index, k=args.k)

    print("\n✅ Ready! Ask questions (type 'exit' to quit).")
    print("💡 First query may stream tokens below as the model generates.")
    
    while True:
        query = input("\nQuestion> ").strip()
        if query.lower() in ("exit", "quit"):
            break
        try:
            print("🤔 Thinking…")
            from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

            # llm is your LlamaCpp instance
            print(">>> Generating a few tokens…")
            llm("Hello, world. This is a test.", callbacks=[StreamingStdOutCallbackHandler()])

            response = qa.invoke({"query": query})
            # Since we're streaming, the answer has already printed token-by-token.
            print()  # just a newline after streaming finishes
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Try rephrasing your question or check model file path.")

if __name__ == "__main__":
    main()
