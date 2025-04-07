from flask import Flask, render_template, request, jsonify
import requests
import os
import re
import time
import sys
import threading
import random
import string
import json
from datetime import datetime
from requests.exceptions import RequestException
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# Global variables to manage tasks
active_tasks = {}
task_lock = threading.Lock()

class FacebookCommenter:
    def __init__(self, task_id):
        self.task_id = task_id
        self.comment_count = 0
        self.start_time = datetime.now()
        self.is_running = True
        self.last_status = "Initializing"
        self.comment_loop = True  # For infinite commenting
        
    def stop_task(self):
        self.is_running = False
        self.comment_loop = False
        
    def get_status(self):
        return {
            "status": "running" if self.is_running else "stopped",
            "comment_count": self.comment_count,
            "uptime": str(datetime.now() - self.start_time),
            "last_status": self.last_status
        }
    
    def extract_post_id(self, url):
        """Extract post ID from various Facebook URL formats"""
        try:
            parsed = urlparse(url)
            
            # Handle standard post URLs
            if "/posts/" in url:
                path_parts = parsed.path.split('/')
                post_index = path_parts.index("posts") + 1
                return path_parts[post_index].split('?')[0]
            
            # Handle photo/video posts
            elif "/photos/" in url or "/videos/" in url:
                return parse_qs(parsed.query).get('fbid', [None])[0]
            
            # Handle permalink/story URLs
            elif "/permalink.php" in url or "/story.php" in url:
                return parse_qs(parsed.query).get('story_fbid', [None])[0]
            
            # Fallback - try to get last numeric part
            last_part = parsed.path.split('/')[-1]
            if last_part.isdigit():
                return last_part
                
            return None
        except Exception as e:
            self.last_status = f"URL parsing error: {str(e)}"
            return None

    def parse_cookies(self, cookie_input):
        """Handle both raw cookies and JSON format"""
        try:
            # Try to parse as JSON
            cookie_data = json.loads(cookie_input)
            if isinstance(cookie_data, dict):
                return "; ".join(f"{k}={v}" for k, v in cookie_data.items())
            elif isinstance(cookie_data, list):
                return [self.parse_cookies(c) for c in cookie_data]
            return cookie_input.strip()
        except json.JSONDecodeError:
            # Treat as raw cookie string
            return cookie_input.strip()

    def verify_cookies(self, cookies):
        """Check if cookies provide valid login"""
        endpoints = [
            'https://mbasic.facebook.com/me',
            'https://www.facebook.com/me'
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(
                    endpoint,
                    cookies={"cookie": cookies},
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36'
                    },
                    timeout=10,
                    allow_redirects=False
                )
                if response.status_code == 200 and 'c_user' in cookies:
                    return True
            except:
                continue
        return False

    def comment_on_post(self, cookies, post_url, comment, hater_name, last_name):
        if not self.is_running:
            return False

        try:
            post_id = self.extract_post_id(post_url)
            if not post_id:
                self.last_status = "<Error> Invalid post URL format"
                return False

            parsed_cookies = self.parse_cookies(cookies)
            if not self.verify_cookies(parsed_cookies):
                self.last_status = "<Error> Invalid cookies - login failed"
                return False

            with requests.Session() as session:
                session.cookies.update({"cookie": parsed_cookies})
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': post_url,
                    'Origin': 'https://www.facebook.com'
                })

                # Try mbasic version first
                mbasic_url = f'https://mbasic.facebook.com/{post_id}'
                response = session.get(mbasic_url, allow_redirects=True)

                # Fallback to www if mbasic fails
                if 'login' in response.url:
                    www_url = f'https://www.facebook.com/{post_id}'
                    response = session.get(www_url, allow_redirects=True)
                    if 'login' in response.url:
                        self.last_status = "<Error> Login required"
                        return False

                # Extract required form parameters
                fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
                jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
                
                if not fb_dtsg or not jazoest:
                    self.last_status = "<Error> Could not find required form fields"
                    return False

                # Prepare comment text
                formatted_comment = f"{hater_name} {comment.strip()} {last_name}"
                
                # Submit comment
                comment_url = f'https://mbasic.facebook.com/a/comment.php?fs=1&parent_comment_id=0&ft_ent_identifier={post_id}'
                
                response = session.post(
                    comment_url,
                    data={
                        'fb_dtsg': fb_dtsg.group(1),
                        'jazoest': jazoest.group(1),
                        'comment_text': formatted_comment
                    },
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': mbasic_url
                    }
                )

                if response.status_code == 200:
                    self.comment_count += 1
                    self.last_status = f"Comment posted: {formatted_comment}"
                    return True
                else:
                    self.last_status = f"Comment failed with status {response.status_code}"
                    return False

        except Exception as e:
            self.last_status = f"<Error> {str(e)}"
            return False

    def run_task(self, config):
        try:
            cookies = config['cookies']
            post_url = config['post_url']
            comments = config['comments']
            delay = config['delay']
            hater_name = config['hater_name']
            last_name = config['last_name']
            
            cookie_index = 0
            comment_index = 0
            
            while self.is_running and self.comment_loop:
                current_cookie = cookies[cookie_index % len(cookies)]
                current_comment = comments[comment_index % len(comments)]
                
                self.comment_on_post(current_cookie, post_url, current_comment, hater_name, last_name)
                
                # Rotate through comments and cookies
                comment_index += 1
                cookie_index += 1
                
                # Random delay to appear more natural
                time.sleep(delay + random.uniform(-2, 2))
                
        except Exception as e:
            self.last_status = f"<Error> {str(e)}"
        finally:
            with task_lock:
                if self.task_id in active_tasks:
                    del active_tasks[self.task_id]

# ... [Keep all the Flask routes from previous version] ...

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=4000, debug=True)
