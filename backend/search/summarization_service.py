#!/usr/bin/env python3
"""
Podcast Summarization Service
Generates detailed summaries of podcast episodes using LLM
"""

import os
import logging
import sqlite3
from typing import Dict, Optional, List
from datetime import datetime
from langchain_ollama import OllamaLLM

logger = logging.getLogger(__name__)

class PodcastSummarizationService:
    def __init__(self, db_path=None, model="llama3"):
        if db_path is None:
            # Default to absolute path from current script location
            from pathlib import Path
            # Go from backend/search to project root, then to data/databases
            current_dir = Path(__file__).parent  # backend/search
            project_root = current_dir.parent.parent  # project root
            db_path = project_root / "data" / "databases" / "podcast_index_v2.db"
            db_path = str(db_path.resolve())  # Convert to absolute path
            
            logger.info(f"🔍 Path resolution debug:")
            logger.info(f"   __file__: {__file__}")
            logger.info(f"   current_dir: {current_dir}")
            logger.info(f"   project_root: {project_root}")
            logger.info(f"   db_path: {db_path}")
        
        self.db_path = db_path
        self.model = model
        self.llm = None
        
        # Validate database exists
        if not os.path.exists(self.db_path):
            logger.error(f"Database not found at: {self.db_path}")
            raise FileNotFoundError(f"Database not found at: {self.db_path}")
        
        logger.info(f"✓ Using database at: {self.db_path}")
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LLM for summarization"""
        try:
            self.llm = OllamaLLM(
                model=self.model,
                temperature=0.3,  # Lower temperature for more consistent summaries
                base_url="http://localhost:11434"
            )
            logger.info("✓ Summarization LLM initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise
    
    def get_podcast_content(self, podcast_id: int) -> Optional[Dict]:
        """Get podcast content from database"""
        try:
            logger.info(f"🔍 Fetching podcast content for ID: {podcast_id}")
            logger.info(f"📁 Database path: {self.db_path}")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # First, check if the podcast ID exists
            cursor.execute('SELECT COUNT(*) FROM podcasts WHERE id = ?', (podcast_id,))
            count = cursor.fetchone()[0]
            logger.info(f"📊 Found {count} podcasts with ID {podcast_id}")
            
            if count == 0:
                # Let's see what podcast IDs we do have
                cursor.execute('SELECT id, title FROM podcasts LIMIT 10')
                available_podcasts = cursor.fetchall()
                logger.info(f"📋 Available podcast IDs: {[p[0] for p in available_podcasts]}")
                logger.info(f"📋 Available podcast titles: {[p[1][:50] + '...' if len(p[1]) > 50 else p[1] for p in available_podcasts]}")
                conn.close()
                return None
            
            cursor.execute('''
                SELECT id, filename, title, content, char_count, indexed_at
                FROM podcasts
                WHERE id = ?
            ''', (podcast_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                logger.error(f"❌ No podcast found with ID: {podcast_id}")
                return None
            
            logger.info(f"✅ Successfully fetched podcast: {row[2][:50]}...")
            
            return {
                'id': row[0],
                'filename': row[1],
                'title': row[2],
                'content': row[3],
                'char_count': row[4],
                'indexed_at': row[5]
            }
        
        except Exception as e:
            logger.error(f"❌ Error fetching podcast content: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def check_existing_summary(self, podcast_id: int) -> Optional[str]:
        """Check if summary already exists in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if summaries table exists, create if not
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    podcast_id INTEGER UNIQUE,
                    summary TEXT NOT NULL,
                    summary_type TEXT DEFAULT 'detailed',
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (podcast_id) REFERENCES podcasts (id)
                )
            ''')
            
            cursor.execute('SELECT summary FROM summaries WHERE podcast_id = ?', (podcast_id,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error checking existing summary: {e}")
            return None
    
    def save_summary(self, podcast_id: int, summary: str) -> bool:
        """Save generated summary to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO summaries (podcast_id, summary, summary_type, generated_at)
                VALUES (?, ?, 'detailed', ?)
            ''', (podcast_id, summary, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✓ Summary saved for podcast {podcast_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving summary: {e}")
            return False
    
    def generate_detailed_summary(self, content: str, title: str) -> str:
        """Generate a detailed summary of the podcast content"""
        
        # For very long content, we might need to chunk it
        max_length = 15000  # Approximate token limit consideration
        if len(content) > max_length:
            # Take the first portion and indicate truncation
            content = content[:max_length] + "\n\n[Content truncated for summarization...]"
        
        prompt = f"""Please create a comprehensive and detailed summary of this podcast episode.

PODCAST TITLE: {title}

REQUIREMENTS:
- Create a professional, well-structured summary suitable for email
- Include an executive summary (2-3 sentences)
- List 5-8 key topics/themes discussed
- Highlight important insights, quotes, or takeaways
- Mention any notable guests or speakers if apparent
- Include actionable advice or recommendations if any
- Keep the tone informative and engaging
- Format with clear sections and bullet points

PODCAST TRANSCRIPT:
{content}

Please provide a detailed summary following the requirements above:"""

        try:
            logger.info("🤖 Generating summary with LLM...")
            summary = self.llm.invoke(prompt)
            logger.info("✓ Summary generated successfully")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    def get_or_generate_summary(self, podcast_id: int, force_regenerate: bool = False) -> Dict:
        """Get existing summary or generate new one"""
        
        # Check for existing summary first (unless forced to regenerate)
        if not force_regenerate:
            existing_summary = self.check_existing_summary(podcast_id)
            if existing_summary:
                logger.info(f"✓ Using cached summary for podcast {podcast_id}")
                return {
                    'success': True,
                    'summary': existing_summary,
                    'cached': True,
                    'podcast_id': podcast_id
                }
        
        # Get podcast content
        podcast = self.get_podcast_content(podcast_id)
        if not podcast:
            return {
                'success': False,
                'error': 'Podcast not found',
                'podcast_id': podcast_id
            }
        
        # Generate new summary
        logger.info(f"🎯 Generating new summary for: {podcast['title']}")
        summary = self.generate_detailed_summary(podcast['content'], podcast['title'])
        
        if summary and not summary.startswith("Error"):
            # Save the summary
            self.save_summary(podcast_id, summary)
            
            return {
                'success': True,
                'summary': summary,
                'cached': False,
                'podcast_id': podcast_id,
                'podcast_title': podcast['title'],
                'podcast_filename': podcast['filename']
            }
        else:
            return {
                'success': False,
                'error': summary,
                'podcast_id': podcast_id
            }

    def generate_summary_for_email(self, podcast_id: int, user_email: str = None) -> Dict:
        """Generate summary formatted specifically for email delivery"""
        
        result = self.get_or_generate_summary(podcast_id)
        
        if not result['success']:
            return result
        
        # Get podcast details
        podcast = self.get_podcast_content(podcast_id)
        if not podcast:
            return {'success': False, 'error': 'Podcast not found'}
        
        # Format for email
        email_content = self._format_summary_for_email(
            result['summary'], 
            podcast['title'], 
            podcast['filename'],
            result.get('cached', False)
        )
        
        return {
            'success': True,
            'email_content': email_content,
            'subject': f"Podcast Summary: {podcast['title']}",
            'podcast_title': podcast['title'],
            'summary': result['summary'],
            'cached': result.get('cached', False)
        }
    
    def _format_summary_for_email(self, summary: str, title: str, filename: str, cached: bool) -> str:
        """Format summary content for email presentation"""
        
        current_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        cache_note = " (from cache)" if cached else " (freshly generated)"
        
        email_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Podcast Summary: {title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .title {{ font-size: 24px; font-weight: bold; margin: 0 0 10px 0; }}
        .meta {{ font-size: 14px; opacity: 0.9; }}
        .summary {{ background: #f8f9fa; padding: 25px; border-radius: 8px; border-left: 4px solid #667eea; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; border-top: 1px solid #eee; margin-top: 30px; }}
        .summary h1, .summary h2, .summary h3 {{ color: #333; }}
        .summary ul, .summary ol {{ margin: 15px 0; }}
        .summary li {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">🎧 Podcast Summary</div>
        <div class="meta">
            <strong>{title}</strong><br>
            Generated on {current_time}{cache_note}
        </div>
    </div>
    
    <div class="summary">
        {self._convert_markdown_to_html(summary)}
    </div>
    
    <div class="footer">
        <p>📁 Source: {filename}</p>
        <p>🤖 Generated by your Podcast Q&A System</p>
        <p>This summary was created using AI and may not capture every detail. For complete information, please refer to the original podcast.</p>
    </div>
</body>
</html>
"""
        return email_html
    
    def _convert_markdown_to_html(self, text: str) -> str:
        """Simple markdown to HTML conversion for email"""
        import re
        
        # Convert headers
        text = re.sub(r'^### (.*$)', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*$)', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*$)', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        
        # Convert bullet points
        text = re.sub(r'^\* (.*$)', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^- (.*$)', r'<li>\1</li>', text, flags=re.MULTILINE)
        
        # Wrap consecutive list items in ul tags
        text = re.sub(r'(<li>.*?</li>(?:\s*<li>.*?</li>)*)', r'<ul>\1</ul>', text, flags=re.DOTALL)
        
        # Convert line breaks to paragraphs
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
                para = f'<p>{para}</p>'
            formatted_paragraphs.append(para)
        
        return '\n'.join(formatted_paragraphs)

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    summarizer = PodcastSummarizationService()
    
    # Test with a podcast ID (replace with actual ID from your database)
    test_podcast_id = 1
    result = summarizer.generate_summary_for_email(test_podcast_id)
    
    if result['success']:
        print("✓ Summary generated successfully!")
        print(f"Subject: {result['subject']}")
        print("\nEmail content preview:")
        print(result['email_content'][:500] + "...")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")