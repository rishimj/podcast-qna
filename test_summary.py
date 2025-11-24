#!/usr/bin/env python3
"""
Test script for podcast summarization functionality
"""

import requests
import json
import sys
import sqlite3
from pathlib import Path

API_BASE = 'http://localhost:3000/api'

def test_database_connection():
    """Test if we can connect to the database"""
    print("🔍 Testing database connection...")
    
    db_path = Path("data/databases/podcast_index_v2.db")
    if not db_path.exists():
        print(f"❌ Database not found at: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM podcasts')
        count = cursor.fetchone()[0]
        
        cursor.execute('SELECT id, title FROM podcasts LIMIT 5')
        podcasts = cursor.fetchall()
        
        conn.close()
        
        print(f"✅ Database connected - {count} podcasts found")
        print("📋 Sample podcasts:")
        for pod_id, title in podcasts:
            print(f"  ID {pod_id}: {title[:60]}...")
        
        return podcasts[0] if podcasts else None
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_api_health():
    """Test API health"""
    print("\n🩺 Testing API health...")
    
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("✅ API is healthy")
            print(f"   Services: {data.get('services', {})}")
            print(f"   Database: {data.get('database', {})}")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API connection error: {e}")
        return False

def test_search_functionality():
    """Test search to get a valid podcast ID"""
    print("\n🔍 Testing search functionality...")
    
    try:
        response = requests.post(f"{API_BASE}/search", 
                               json={"query": "AI", "top_k": 3}, 
                               timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            if results:
                print(f"✅ Search successful - {len(results)} results")
                for i, result in enumerate(results):
                    print(f"  {i+1}. ID {result['podcast_id']}: {result['title'][:50]}...")
                return results[0]  # Return first result
            else:
                print("❌ No search results found")
                return None
        else:
            print(f"❌ Search failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Search error: {e}")
        return None

def test_summary_generation(podcast_id):
    """Test summary generation"""
    print(f"\n🤖 Testing summary generation for podcast ID: {podcast_id}...")
    
    try:
        response = requests.post(f"{API_BASE}/summary/generate",
                               json={"podcast_id": podcast_id},
                               timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Summary generation successful")
                print(f"   Podcast: {data.get('podcast_title', 'Unknown')}")
                print(f"   Cached: {data.get('cached', False)}")
                print(f"   Generation time: {data.get('generation_time_ms', 0)}ms")
                print(f"   Summary length: {len(data.get('summary', ''))}")
                return True
            else:
                print(f"❌ Summary generation failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Summary API error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Summary generation error: {e}")
        return False

def test_email_summary(podcast_id, test_email="test@example.com"):
    """Test email summary (dry run)"""
    print(f"\n📧 Testing email summary for podcast ID: {podcast_id}...")
    print(f"   Test email: {test_email}")
    
    try:
        response = requests.post(f"{API_BASE}/summary/email",
                               json={
                                   "podcast_id": podcast_id,
                                   "email": test_email
                               },
                               timeout=90)
        
        print(f"   Response status: {response.status_code}")
        print(f"   Response: {response.text[:500]}...")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Email summary API successful")
                return True
            else:
                print(f"❌ Email summary failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Email summary API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Email summary error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Podcast Summary System Tests")
    print("=" * 50)
    
    # Test database
    sample_podcast = test_database_connection()
    if not sample_podcast:
        print("❌ Database test failed - cannot continue")
        sys.exit(1)
    
    # Test API health
    if not test_api_health():
        print("❌ API health test failed - make sure Flask server is running")
        sys.exit(1)
    
    # Test search to get a valid podcast
    search_result = test_search_functionality()
    if search_result:
        podcast_id = search_result['podcast_id']
        podcast_title = search_result['title']
    else:
        # Fallback to database sample
        podcast_id = sample_podcast[0]
        podcast_title = sample_podcast[1]
    
    print(f"\n🎯 Using podcast for tests:")
    print(f"   ID: {podcast_id}")
    print(f"   Title: {podcast_title}")
    
    # Test summary generation
    if not test_summary_generation(podcast_id):
        print("❌ Summary generation failed")
        sys.exit(1)
    
    # Test email summary
    test_email = input("\n📧 Enter email for test (or press Enter for dry run): ").strip()
    if not test_email:
        test_email = "test@example.com"
    
    test_email_summary(podcast_id, test_email)
    
    print("\n🎉 Tests completed!")

if __name__ == "__main__":
    main()