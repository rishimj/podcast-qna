#!/usr/bin/env python3
"""
Email Service for Podcast Summaries
Handles sending podcast summaries via email using SMTP
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.from_name = "Podcast Q&A System"
        
        self._validate_config()
    
    def _validate_config(self):
        """Validate email configuration"""
        required_vars = ['SMTP_USERNAME', 'SMTP_PASSWORD']
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            logger.warning(f"Missing email configuration: {missing}")
            logger.warning("Email functionality will not work without proper SMTP configuration")
        else:
            logger.info("✓ Email service configured")
    
    def test_connection(self) -> Dict:
        """Test SMTP connection"""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.quit()
            
            return {
                'success': True,
                'message': 'SMTP connection successful'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'SMTP connection failed: {str(e)}'
            }
    
    def send_summary_email(self, to_email: str, subject: str, html_content: str, 
                          podcast_title: str = None) -> Dict:
        """Send podcast summary email"""
        
        if not self.smtp_username or not self.smtp_password:
            return {
                'success': False,
                'error': 'Email service not configured. Please set SMTP credentials in config.env'
            }
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Create plain text version as fallback
            plain_text = self._html_to_text(html_content)
            
            # Create the email parts
            part1 = MIMEText(plain_text, 'plain')
            part2 = MIMEText(html_content, 'html')
            
            # Add parts to message
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            logger.info(f"📧 Sending summary email to {to_email}")
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            
            text = msg.as_string()
            server.sendmail(self.from_email, to_email, text)
            server.quit()
            
            logger.info(f"✓ Summary email sent successfully to {to_email}")
            
            return {
                'success': True,
                'message': f'Summary sent to {to_email}',
                'to_email': to_email,
                'subject': subject,
                'sent_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {
                'success': False,
                'error': f'Failed to send email: {str(e)}',
                'to_email': to_email
            }
    
    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML content to plain text for email fallback"""
        import re
        
        # Remove HTML tags
        text = re.sub('<[^<]+?>', '', html_content)
        
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()
        
        return text
    
    def send_test_email(self, to_email: str) -> Dict:
        """Send a test email to verify configuration"""
        
        subject = "Podcast Q&A System - Test Email"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎧 Podcast Q&A System</h1>
        <p>Email Service Test</p>
    </div>
    <div class="content">
        <p>Hello!</p>
        <p>This is a test email from your Podcast Q&A System to verify that email functionality is working correctly.</p>
        <p><strong>Test Details:</strong></p>
        <ul>
            <li>Sent to: {to_email}</li>
            <li>Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            <li>SMTP Server: {self.smtp_host}:{self.smtp_port}</li>
        </ul>
        <p>If you received this email, your email configuration is working properly and you're ready to receive podcast summaries!</p>
        <p>Best regards,<br>Your Podcast Q&A System</p>
    </div>
</body>
</html>
"""
        
        return self.send_summary_email(to_email, subject, html_content)

    def create_summary_email_template(self, podcast_title: str, summary_content: str, 
                                    generated_at: str, cached: bool = False) -> str:
        """Create a professional email template for podcast summaries"""
        
        cache_badge = "📋 Cached" if cached else "🆕 Fresh"
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            line-height: 1.6; 
            color: #333; 
            margin: 0; 
            padding: 0; 
            background-color: #f5f5f5;
        }}
        .container {{ 
            max-width: 800px; 
            margin: 0 auto; 
            background: white; 
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        .header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; 
            padding: 40px 30px; 
            text-align: center;
        }}
        .title {{ 
            font-size: 28px; 
            font-weight: bold; 
            margin: 0 0 10px 0; 
        }}
        .subtitle {{ 
            font-size: 16px; 
            opacity: 0.9; 
            margin: 0;
        }}
        .meta {{ 
            background: #f8f9fa; 
            padding: 20px 30px; 
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .summary {{ 
            padding: 30px; 
        }}
        .summary h1 {{ 
            color: #2c3e50; 
            border-bottom: 2px solid #667eea; 
            padding-bottom: 10px;
        }}
        .summary h2 {{ 
            color: #34495e; 
            margin-top: 30px;
        }}
        .summary h3 {{ 
            color: #7f8c8d; 
        }}
        .summary ul, .summary ol {{ 
            margin: 15px 0; 
            padding-left: 20px;
        }}
        .summary li {{ 
            margin: 8px 0; 
        }}
        .footer {{ 
            background: #2c3e50; 
            color: white; 
            text-align: center; 
            padding: 30px; 
            font-size: 14px;
        }}
        .badge {{ 
            background: #28a745; 
            color: white; 
            padding: 4px 8px; 
            border-radius: 12px; 
            font-size: 12px; 
            font-weight: bold;
        }}
        .badge.cached {{ 
            background: #17a2b8; 
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">🎧 Podcast Summary</div>
            <div class="subtitle">{podcast_title}</div>
        </div>
        
        <div class="meta">
            <div>
                <strong>📅 Generated:</strong> {generated_at}
            </div>
            <div>
                <span class="badge {'cached' if cached else ''}">{cache_badge}</span>
            </div>
        </div>
        
        <div class="summary">
            {summary_content}
        </div>
        
        <div class="footer">
            <p><strong>🤖 Generated by your Podcast Q&A System</strong></p>
            <p>This AI-generated summary captures key points but may not include every detail.</p>
            <p>For the complete experience, listen to the full podcast episode.</p>
        </div>
    </div>
</body>
</html>
"""

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Load environment variables for testing
    from pathlib import Path
    config_path = Path(__file__).parent.parent.parent / 'config' / 'env' / 'config.env'
    
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    email_service = EmailService()
    
    # Test connection
    result = email_service.test_connection()
    print(f"Connection test: {result}")
    
    # Send test email (uncomment to test)
    # test_email = "your-email@example.com"
    # result = email_service.send_test_email(test_email)
    # print(f"Test email result: {result}")