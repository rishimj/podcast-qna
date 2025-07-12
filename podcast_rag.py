#!/usr/bin/env python3
"""
Podcast RAG Chatbot using Llama 3
For M1 Mac with Ollama

Setup:
1. brew install ollama
2. ollama pull llama3
3. ollama serve
4. pip install langchain langchain-ollama
5. Create 'transcripts' folder with .txt files
"""

import sys
import os
import glob
from langchain_ollama import OllamaLLM

def list_transcripts(folder="transcripts"):
    """List available transcript files"""
    try:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created {folder}/ directory. Add .txt transcript files there.")
            return []
        
        files = glob.glob(os.path.join(folder, "*.txt"))
        if not files:
            print(f"No transcript files found in {folder}/")
            return []
        
        transcripts = [os.path.basename(f) for f in files]
        return sorted(transcripts)
    
    except Exception as e:
        print(f"Error listing transcripts: {e}")
        return []

def load_transcript(filename, folder="transcripts"):
    """Load a specific transcript file"""
    try:
        filepath = os.path.join(folder, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read().strip()
            print(f"\n✓ Loaded {len(content)} characters from {filename}")
            return content
        else:
            print(f"Transcript {filename} not found")
            return None
    except Exception as e:
        print(f"Error loading transcript: {e}")
        return None

def create_chatbot():
    """Initialize the chatbot"""
    try:
        llm = OllamaLLM(
            model="llama3",
            temperature=0.7,
            base_url="http://localhost:11434"
        )
        return llm
    
    except Exception as e:
        print(f"Error initializing chatbot: {e}")
        print("\nMake sure:")
        print("1. Ollama is installed: brew install ollama")
        print("2. Llama 3 is downloaded: ollama pull llama3")
        print("3. Ollama is running: ollama serve")
        sys.exit(1)

def get_multiline_input():
    """Get multi-line input from user"""
    print("You: ", end="", flush=True)
    lines = []
    
    try:
        while True:
            line = input()
            if line == "END":
                break
            lines.append(line)
            
            if len(lines) == 1 and not line.endswith("\\"):
                break
    
    except EOFError:
        pass
    
    return "\n".join(lines)

def display_menu(current_transcript):
    """Display status and commands"""
    print("\n" + "="*50)
    if current_transcript:
        print(f"📎 Loaded: {current_transcript}")
    else:
        print("📎 No transcript loaded")
    
    print("\nCommands:")
    print("- 'list' - Show available transcripts")
    print("- 'load <filename>' - Load a transcript") 
    print("- 'clear' - Clear loaded transcript")
    print("- 'quit' - Exit")
    print("="*50 + "\n")

def main():
    """Main chat loop"""
    print("🎙️  Podcast RAG Chatbot")
    print("Ask questions about your podcast transcripts!\n")
    
    llm = create_chatbot()
    current_transcript = None
    current_content = None
    conversation_history = []
    
    # Test connection
    try:
        test_response = llm.invoke("Hello")
        print("✓ Chatbot ready!\n")
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)
    
    # List transcripts
    transcripts = list_transcripts()
    if transcripts:
        print(f"Found transcripts: {', '.join(transcripts)}")
    
    display_menu(current_transcript)
    
    while True:
        try:
            user_input = get_multiline_input().strip()
            
            # Commands
            if user_input.lower() in ['quit', 'exit']:
                print("Goodbye!")
                break
            
            elif user_input.lower() == 'list':
                transcripts = list_transcripts()
                if transcripts:
                    print("\n📁 Available transcripts:")
                    for t in transcripts:
                        print(f"  - {t}")
                continue
            
            elif user_input.lower().startswith('load '):
                filename = user_input[5:].strip()
                content = load_transcript(filename)
                if content:
                    current_transcript = filename
                    current_content = content
                    print(f"Preview: {content[:300]}...")
                    print(f"\n✓ Ready to answer questions about this podcast!")
                    # Clear history when loading new transcript
                    conversation_history = []
                continue
            
            elif user_input.lower() == 'clear':
                current_transcript = None
                current_content = None
                conversation_history = []
                print("✓ Transcript cleared")
                continue
            
            if not user_input:
                continue
            
            # Build prompt with system message, transcript, and conversation
            if current_content:
                # Build conversation history string
                history_str = ""
                for h in conversation_history[-5:]:  # Keep last 5 exchanges
                    history_str += f"Human: {h['human']}\nAssistant: {h['assistant']}\n\n"
                
                prompt = f"""You are a helpful assistant for answering questions about podcasts based on their transcripts.

IMPORTANT INSTRUCTIONS:
- Answer questions based ONLY on the podcast transcript provided below
- If information is not in the transcript, say "I don't find that information in the transcript"
- Quote relevant parts from the transcript when answering
- Be specific and accurate

PODCAST TRANSCRIPT:
{current_content}

CONVERSATION HISTORY:
{history_str}

CURRENT QUESTION: {user_input}

Please answer the question based on the podcast transcript above."""
                
                print(f"\n📤 Processing with {len(current_content)} chars of transcript...")
            else:
                prompt = f"No podcast transcript loaded. Please load a transcript first using 'load <filename>'. User said: {user_input}"
            
            # Get response
            response = llm.invoke(prompt)
            
            # Save to history
            if current_content:
                conversation_history.append({
                    'human': user_input,
                    'assistant': response
                })
            
            print(f"\nChatbot: {response}\n")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            print("Try again.\n")

if __name__ == "__main__":
    main()