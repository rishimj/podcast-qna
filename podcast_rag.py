#!/usr/bin/env python3
"""
Simple Llama 3 Chatbot with Transcript Loading
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
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain

def list_transcripts(folder="transcripts"):
    """List available transcript files"""
    try:
        # Create folder if it doesn't exist
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created {folder}/ directory. Add .txt transcript files there.")
            return []
        
        # Find all .txt files
        files = glob.glob(os.path.join(folder, "*.txt"))
        if not files:
            print(f"No transcript files found in {folder}/")
            return []
        
        # Extract just filenames
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
            return content
        else:
            print(f"Transcript {filename} not found")
            return None
    except Exception as e:
        print(f"Error loading transcript: {e}")
        return None

def create_chatbot():
    """Initialize the chatbot with error handling"""
    try:
        # Initialize Llama 3 via Ollama
        llm = OllamaLLM(
            model="llama3",
            temperature=0.7,
            base_url="http://localhost:11434"
        )
        
        # Create conversation chain with memory
        memory = ConversationBufferMemory()
        chatbot = ConversationChain(
            llm=llm,
            memory=memory,
            verbose=False
        )
        
        return chatbot
    
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
            
            # Single line input
            if len(lines) == 1 and not line.endswith("\\"):
                break
    
    except EOFError:
        pass
    
    return "\n".join(lines)

def display_menu(transcripts, current_transcript):
    """Display available commands and current status"""
    print("\n" + "="*50)
    if current_transcript:
        print(f"Current transcript: {current_transcript}")
    else:
        print("No transcript loaded")
    
    print("\nCommands:")
    print("- 'list' - Show available transcripts")
    print("- 'load <filename>' - Load a transcript")
    print("- 'clear' - Clear loaded transcript")
    print("- 'quit' or 'exit' - Exit program")
    print("="*50 + "\n")

def main():
    """Main chat loop"""
    print("Llama 3 RAG Chatbot - Step 1: Transcript Loader")
    
    # Initialize
    chatbot = create_chatbot()
    current_transcript = None
    current_content = None
    
    # Test connection
    try:
        chatbot.predict(input="Hello")
        print("\nChatbot ready!")
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)
    
    # List available transcripts on start
    transcripts = list_transcripts()
    if transcripts:
        print(f"\nAvailable transcripts: {', '.join(transcripts)}")
    
    display_menu(transcripts, current_transcript)
    
    # Chat loop
    while True:
        try:
            # Get user input
            user_input = get_multiline_input().strip()
            
            # Check for commands
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("Goodbye!")
                break
            
            elif user_input.lower() == 'list':
                transcripts = list_transcripts()
                if transcripts:
                    print("\nAvailable transcripts:")
                    for t in transcripts:
                        print(f"  - {t}")
                continue
            
            elif user_input.lower().startswith('load '):
                filename = user_input[5:].strip()
                content = load_transcript(filename)
                if content:
                    current_transcript = filename
                    current_content = content
                    print(f"Loaded transcript: {filename}")
                    print(f"Content preview: {content[:200]}...")
                continue
            
            elif user_input.lower() == 'clear':
                current_transcript = None
                current_content = None
                print("Transcript cleared")
                continue
            
            # Skip empty input
            if not user_input:
                continue
            
            # Build prompt with transcript context if available
            if current_content:
                full_input = f"Context from transcript '{current_transcript}':\n{current_content}\n\nUser question: {user_input}"
            else:
                full_input = user_input
            
            # Show thinking for long inputs
            if len(full_input) > 500:
                print("Chatbot: Thinking...", end="", flush=True)
            
            # Get response
            response = chatbot.predict(input=full_input)
            
            # Clear thinking indicator
            if len(full_input) > 500:
                print("\r", end="")
            
            print(f"Chatbot: {response}\n")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            print("Something went wrong. Try again.\n")

if __name__ == "__main__":
    main()