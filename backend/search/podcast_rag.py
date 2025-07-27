#!/usr/bin/env python3
"""
Podcast RAG Chatbot with Two-Tiered Search
Uses enhanced semantic search for better accuracy
"""

import sys
import os
from langchain_ollama import OllamaLLM
from podcast_semantic_search_complete import PodcastTwoTierSearch

def create_chatbot():
    """Initialize the Llama chatbot"""
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

def get_user_input(prompt="You: "):
    """Get single or multi-line input from user"""
    print(prompt, end="", flush=True)
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

def display_search_results(results, query):
    """Display search results with score breakdown"""
    print(f"\n🔍 Search results for: '{query}'\n")
    
    for i, result in enumerate(results[:3], 1):
        print(f"{i}. {result['title']} (confidence: {result['final_score']:.2%})")
        print(f"   File: {result['filename']}")
        
        # Show what matched
        if result['title_similarity'] > 0.7:
            print(f"   ✓ Strong title match ({result['title_similarity']:.2%})")
        elif result['intro_similarity'] > 0.7:
            print(f"   ✓ Strong intro match ({result['intro_similarity']:.2%})")
        elif result['chunks_similarity'] > 0.7:
            print(f"   ✓ Strong content match ({result['chunks_similarity']:.2%})")
        
        print()

def main():
    """Main chat loop with two-tiered search"""
    print("🎙️  Podcast RAG Chatbot with Enhanced Search")
    print("="*50)
    
    # Initialize systems
    llm = create_chatbot()
    search_system = PodcastTwoTierSearch()
    
    # Test connections
    try:
        test_response = llm.invoke("Hello")
        print("✓ Chatbot ready!")
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)
    
    # Check database stats
    stats = search_system.get_stats()
    if stats['podcasts'] == 0:
        print("\n⚠️  No podcasts indexed yet!")
        print("Run this first to index your podcasts:")
        print("  python podcast_two_tier_search.py")
        search_system.close()
        sys.exit(1)
    
    print(f"✓ Found {stats['podcasts']} indexed podcasts")
    if stats['title_embeddings'] < stats['podcasts']:
        print(f"⚠️  Only {stats['title_embeddings']} have enhanced embeddings")
        print("   Run podcast_two_tier_search.py to add title embeddings")
    
    # Get podcast selection using two-tiered search
    print("\nWhat podcast would you like to ask questions about?")
    print("(You can use the title, topic, guest name, or describe the content)")
    
    podcast_query = get_user_input("🔍 ").strip()
    
    if not podcast_query:
        print("No podcast specified. Exiting.")
        search_system.close()
        sys.exit(1)
    
    # Find matching podcasts using two-tiered search
    print(f"\n🤔 Searching...")
    
    results = search_system.search_two_tier(podcast_query, top_k=3)
    
    if not results:
        print(f"\n❌ No podcast found matching '{podcast_query}'")
        search_system.close()
        sys.exit(1)
    
    # Display results
    display_search_results(results, podcast_query)
    
    # Select podcast
    best_match = results[0]
    
    # If confidence is low or multiple good matches, let user choose
    if best_match['final_score'] < 0.5 or (len(results) > 1 and results[1]['final_score'] > 0.4):
        print("Multiple possible matches found.")
        choice = input("Select podcast (1-3) or press Enter for best match: ").strip()
        
        if choice in ['1', '2', '3']:
            idx = int(choice) - 1
            if idx < len(results):
                best_match = results[idx]
    
    # Get full podcast content
    cursor = search_system.conn.cursor()
    cursor.execute("SELECT content FROM podcasts WHERE id = ?", (best_match['podcast_id'],))
    current_content = cursor.fetchone()[0]
    
    if not current_content:
        print("Error loading podcast content. Exiting.")
        search_system.close()
        sys.exit(1)
    
    print(f"\n✅ Selected: {best_match['title']}")
    print(f"📎 Ready to answer questions about this podcast!")
    print("\nCommands: 'quit' to exit, 'search' for another podcast, 'debug' to see search details\n")
    print("="*50 + "\n")
    
    # Main Q&A loop
    conversation_history = []
    
    while True:
        try:
            user_input = get_user_input().strip()
            
            if user_input.lower() in ['quit', 'exit']:
                print("\nGoodbye!")
                break
            
            elif user_input.lower() == 'search':
                # Search for another podcast
                print("\nWhat other podcast would you like to discuss?")
                new_query = get_user_input("🔍 ").strip()
                
                if new_query:
                    print(f"\n🤔 Searching...")
                    new_results = search_system.search_two_tier(new_query, top_k=3)
                    
                    if new_results:
                        display_search_results(new_results, new_query)
                        
                        # Select from results
                        if len(new_results) > 1:
                            choice = input("Select podcast (1-3) or press Enter for best match: ").strip()
                            if choice in ['1', '2', '3'] and int(choice) <= len(new_results):
                                new_match = new_results[int(choice)-1]
                            else:
                                new_match = new_results[0]
                        else:
                            new_match = new_results[0]
                        
                        # Load new content
                        cursor.execute("SELECT content FROM podcasts WHERE id = ?", 
                                     (new_match['podcast_id'],))
                        current_content = cursor.fetchone()[0]
                        
                        if current_content:
                            best_match = new_match
                            conversation_history = []  # Reset conversation
                            print(f"\n✅ Switched to: {best_match['title']}")
                            print("="*50 + "\n")
                        else:
                            print("❌ Error loading podcast")
                    else:
                        print("❌ No matching podcast found")
                continue
            
            elif user_input.lower() == 'debug':
                # Show detailed search breakdown
                print(f"\n📊 Current podcast scoring breakdown:")
                print(f"Title: {best_match['title']}")
                print(f"Title match: {best_match['title_similarity']:.3f} (60% weight)")
                print(f"Intro match: {best_match['intro_similarity']:.3f} (20% weight)")
                print(f"Content match: {best_match['chunks_similarity']:.3f} (15% weight)")
                print(f"Outro match: {best_match['outro_similarity']:.3f} (5% weight)")
                print(f"Final score: {best_match['final_score']:.3f}")
                continue
            
            elif user_input.lower() == 'info':
                # Show current podcast info
                print(f"\n📎 Current Podcast: {best_match['title']}")
                print(f"   File: {best_match['filename']}")
                print(f"   Match confidence: {best_match['final_score']:.2%}")
                print(f"   Content length: {len(current_content)} characters")
                continue
            
            if not user_input:
                continue
            
            # Build prompt with conversation history
            history_str = ""
            for h in conversation_history[-5:]:  # Keep last 5 exchanges
                history_str += f"Human: {h['human']}\nAssistant: {h['assistant']}\n\n"
            
            prompt = f"""You are a helpful assistant for answering questions about podcasts based on their transcripts.

IMPORTANT INSTRUCTIONS:
- Answer questions based ONLY on the podcast transcript provided below
- If information is not in the transcript, say "I don't find that information in the transcript"
- Quote relevant parts from the transcript when answering
- Be specific and accurate
- The podcast is titled: {best_match['title']}

PODCAST TRANSCRIPT:
{current_content}

CONVERSATION HISTORY:
{history_str}

CURRENT QUESTION: {user_input}

Please answer the question based on the podcast transcript above."""
            
            # Get response
            print("\n🤔 Thinking...")
            response = llm.invoke(prompt)
            
            # Save to history
            conversation_history.append({
                'human': user_input,
                'assistant': response
            })
            
            print(f"\n💬 {response}\n")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            print("Try again.\n")
    
    # Cleanup
    search_system.close()


if __name__ == "__main__":
    main()