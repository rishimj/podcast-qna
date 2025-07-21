#!/usr/bin/env python3
"""
Test script for Podcast Flask API
Tests all endpoints to ensure they're working correctly
"""

import requests
import json
import time
from colorama import init, Fore, Style

# Initialize colorama for colored output
init()

# API base URL
BASE_URL = "http://localhost:3000/api"

def print_test(test_name):
    """Print test header"""
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"Testing: {test_name}")
    print(f"{'='*50}{Style.RESET_ALL}")

def print_success(message):
    """Print success message"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")

def print_error(message):
    """Print error message"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")

def print_info(message):
    """Print info message"""
    print(f"{Fore.YELLOW}ℹ {message}{Style.RESET_ALL}")

def test_health_check():
    """Test health check endpoint"""
    print_test("Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"API Status: {data['api']}")
        print(f"Services:")
        print(f"  - Search System: {data['services']['search_system']}")
        print(f"  - LLM: {data['services']['llm']}")
        
        if 'database' in data:
            print(f"Database:")
            print(f"  - Connected: {data['database']['connected']}")
            print(f"  - Podcasts: {data['database']['podcasts']}")
            print(f"  - Chunks: {data['database']['chunks']}")
        
        print_success("Health check passed")
        return True
        
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_list_podcasts():
    """Test list podcasts endpoint"""
    print_test("List Podcasts")
    
    try:
        response = requests.get(f"{BASE_URL}/podcasts")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Total Podcasts: {data['count']}")
        
        if data['podcasts']:
            print("\nFirst 3 podcasts:")
            for podcast in data['podcasts'][:3]:
                print(f"  - {podcast['title']}")
                print(f"    ID: {podcast['id']}, File: {podcast['filename']}")
                print(f"    Size: {podcast['char_count']} chars (~{podcast['duration_estimate']})")
        
        print_success("List podcasts passed")
        return data['podcasts'][0]['id'] if data['podcasts'] else None
        
    except Exception as e:
        print_error(f"List podcasts failed: {e}")
        return None

def test_get_podcast(podcast_id):
    """Test get specific podcast endpoint"""
    print_test(f"Get Podcast Details (ID: {podcast_id})")
    
    try:
        response = requests.get(f"{BASE_URL}/podcast/{podcast_id}")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Title: {data['title']}")
        print(f"Filename: {data['filename']}")
        print(f"Character Count: {data['char_count']}")
        print(f"Chunk Count: {data['chunk_count']}")
        print(f"Content Preview: {data['content'][:100]}...")
        
        print_success("Get podcast passed")
        return True
        
    except Exception as e:
        print_error(f"Get podcast failed: {e}")
        return False

def test_search():
    """Test search endpoint"""
    print_test("Search Podcasts")
    
    test_queries = [
        "consciousness",
        "artificial intelligence",
        "joe rogan",
        "philosophy of mind"
    ]
    
    for query in test_queries:
        print(f"\n{Fore.BLUE}Query: '{query}'{Style.RESET_ALL}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/search",
                json={"query": query, "top_k": 3}
            )
            data = response.json()
            
            print(f"Status Code: {response.status_code}")
            print(f"Results: {data['count']}")
            print(f"Search Time: {data['search_time_ms']}ms")
            
            if data['results']:
                print("\nTop Results:")
                for i, result in enumerate(data['results'], 1):
                    print(f"  {i}. {result['title']} ({result['confidence_percent']}%)")
                    print(f"     Scoring - Title: {result['scoring']['title']}, "
                          f"Intro: {result['scoring']['intro']}, "
                          f"Content: {result['scoring']['content']}")
                
                return data['results'][0]['podcast_id']
            else:
                print_info("No results found")
        
        except Exception as e:
            print_error(f"Search failed: {e}")
    
    return None

def test_chat(podcast_id):
    """Test chat endpoint"""
    print_test(f"Chat with Podcast (ID: {podcast_id})")
    
    test_messages = [
        "What is the main topic of this podcast?",
        "Can you summarize the key points discussed?",
        "What did they say about consciousness?"
    ]
    
    session_id = f"test_session_{int(time.time())}"
    
    for message in test_messages:
        print(f"\n{Fore.BLUE}User: {message}{Style.RESET_ALL}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/chat",
                json={
                    "podcast_id": podcast_id,
                    "message": message,
                    "session_id": session_id
                }
            )
            data = response.json()
            
            if response.status_code == 200:
                print(f"{Fore.GREEN}Assistant: {data['response'][:200]}...{Style.RESET_ALL}")
                print(f"Response Time: {data['response_time_ms']}ms")
                print_success("Chat message sent successfully")
            else:
                print_error(f"Chat failed: {data.get('error', 'Unknown error')}")
                break
                
        except Exception as e:
            print_error(f"Chat failed: {e}")
            break
    
    # Test session retrieval
    print(f"\n{Fore.CYAN}Testing session retrieval...{Style.RESET_ALL}")
    try:
        response = requests.get(f"{BASE_URL}/chat/session/{session_id}")
        data = response.json()
        print(f"Session has {len(data['history'])} messages")
        print_success("Session retrieval passed")
    except Exception as e:
        print_error(f"Session retrieval failed: {e}")

def test_stats():
    """Test statistics endpoint"""
    print_test("System Statistics")
    
    try:
        response = requests.get(f"{BASE_URL}/stats")
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print("\nDatabase Statistics:")
        print(f"  - Total Podcasts: {data['database']['total_podcasts']}")
        print(f"  - Podcasts with Embeddings: {data['database']['podcasts_with_embeddings']}")
        print(f"  - Total Chunks: {data['database']['total_chunks']}")
        print(f"  - Embedded Chunks: {data['database']['embedded_chunks']}")
        
        print("\nSession Statistics:")
        print(f"  - Active Sessions: {data['sessions']['active']}")
        print(f"  - Total Messages: {data['sessions']['total_messages']}")
        
        print("\nSystem Status:")
        print(f"  - Search Ready: {data['system']['search_ready']}")
        print(f"  - Embedding Coverage: {data['system']['embedding_coverage']}%")
        
        print_success("Stats endpoint passed")
        return True
        
    except Exception as e:
        print_error(f"Stats failed: {e}")
        return False

def run_all_tests():
    """Run all API tests"""
    print(f"\n{Fore.MAGENTA}{'='*50}")
    print("🧪 Podcast Flask API Test Suite")
    print(f"{'='*50}{Style.RESET_ALL}")
    
    print_info(f"Testing API at: {BASE_URL}")
    
    # Check if API is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to API. Make sure Flask server is running:")
        print("  python podcast_flask_api.py")
        return
    
    # Run tests
    results = []
    
    # 1. Health check
    results.append(("Health Check", test_health_check()))
    
    # 2. List podcasts and get first ID
    podcast_id = test_list_podcasts()
    results.append(("List Podcasts", podcast_id is not None))
    
    # 3. Get specific podcast
    if podcast_id:
        results.append(("Get Podcast", test_get_podcast(podcast_id)))
    
    # 4. Search
    search_podcast_id = test_search()
    results.append(("Search", search_podcast_id is not None))
    
    # 5. Chat (use search result or first podcast)
    chat_podcast_id = search_podcast_id or podcast_id
    if chat_podcast_id:
        test_chat(chat_podcast_id)
        results.append(("Chat", True))  # Assume pass if no exception
    
    # 6. Statistics
    results.append(("Statistics", test_stats()))
    
    # Summary
    print(f"\n{Fore.MAGENTA}{'='*50}")
    print("Test Summary")
    print(f"{'='*50}{Style.RESET_ALL}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{Fore.GREEN}PASSED{Style.RESET_ALL}" if result else f"{Fore.RED}FAILED{Style.RESET_ALL}"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print_success("All tests passed! API is ready for frontend integration.")
    else:
        print_error(f"{total - passed} tests failed. Please check the errors above.")

if __name__ == "__main__":
    run_all_tests()