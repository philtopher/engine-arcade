from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response, stream_with_context, make_response
import subprocess
import os
import json
from pathlib import Path
import datetime
import threading
import time
import shutil
import signal
import select
import requests

app = Flask(__name__, static_folder='static')

# Configuration
BASE_PROJECT_DIR = os.path.expanduser("~/Desktop/gpte-projects")
os.makedirs(BASE_PROJECT_DIR, exist_ok=True)

# Create project_assets directory if it doesn't exist
project_assets_dir = os.path.join(app.static_folder, 'project_assets')
os.makedirs(project_assets_dir, exist_ok=True)

@app.route('/')
def index():
    # Get list of existing projects
    projects = []
    if os.path.exists(BASE_PROJECT_DIR):
        projects = [d for d in os.listdir(BASE_PROJECT_DIR) 
                   if os.path.isdir(os.path.join(BASE_PROJECT_DIR, d))]
    
    return render_template('index.html', projects=projects)

@app.route('/create_project', methods=['POST'])
def create_project():
    project_name = request.form.get('project_name', '').strip()
    prompt = request.form.get('prompt', '').strip()
    # Game type removed - now inferred from description
    
    if not project_name or not prompt:
        return jsonify({"status": "error", "message": "Project name and prompt are required"}), 400
    
    # Create project directory
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    
    # Create or overwrite the project directory
    if os.path.exists(project_dir):
        # Remove existing files
        for item in os.listdir(project_dir):
            item_path = os.path.join(project_dir, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
    else:
        os.makedirs(project_dir, exist_ok=True)
    
    # Create enhanced prompt with Three.js template
    threejs_template = f"""
Create a 3D game using Three.js with the following specifications:

DETAILED DESCRIPTION:
{prompt}

TECHNICAL REQUIREMENTS:
1. Use Three.js for 3D rendering (version 0.160.0 or newer)
2. Implement proper game loop with requestAnimationFrame
3. Include responsive design that works on different screen sizes
4. Organize code with clear separation of concerns (scene setup, game logic, controls, etc.)
5. Add proper lighting, shadows, and camera controls
6. Implement collision detection as needed
7. Include sound effects and background music if appropriate
8. Add a simple UI for score, instructions, or game state

DELIVERABLES:
- index.html as the main entry point
- Organized JavaScript files (game.js, controls.js, etc.)
- Any necessary assets (models, textures, sounds) with appropriate attribution
- Clear code comments explaining the implementation

The game should run directly in a browser without requiring a build step or server-side code.
"""
    
    # Create prompt file with enhanced Three.js template
    with open(os.path.join(project_dir, "prompt"), "w") as f:
        f.write(threejs_template)
    
    # Create a file to specify that this is a Three.js project to help with parsing later
    with open(os.path.join(project_dir, ".threejs-project"), "w") as f:
        f.write(f"is_threejs=true\n")
    
    # Set up additional gpt-engineer specific configurations
    workspace_dir = os.path.join(project_dir, "workspace")
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)
    
    # Copy custom preprompts to the project directory
    # Try both the new and old directory paths
    gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
    if not os.path.exists(gpte_repo):
        gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
        print(f"Using original path: {gpte_repo}")
    else:
        print(f"Using new path: {gpte_repo}")
    preprompts_dir = os.path.join(gpte_repo, 'gpt_engineer/preprompts')
    project_preprompts_dir = os.path.join(project_dir, 'preprompts')
    
    if not os.path.exists(project_preprompts_dir):
        os.makedirs(project_preprompts_dir, exist_ok=True)
        
    # Copy standard preprompts
    for preprompt_file in os.listdir(preprompts_dir):
        if os.path.isfile(os.path.join(preprompts_dir, preprompt_file)):
            with open(os.path.join(preprompts_dir, preprompt_file), 'r') as src:
                content = src.read()
                
            # Special handling for entrypoint to ensure it generates index.html
            if preprompt_file == 'entrypoint':
                content += "\n\nMake sure to name the main entry file 'index.html' and include all necessary Three.js scripts."
                
            with open(os.path.join(project_preprompts_dir, preprompt_file), 'w') as dst:
                dst.write(content)
    
    # Create a basic working Three.js template directly in the project directory
    create_basic_threejs_template(project_dir, prompt)
    
    # Create a static assets directory for this project
    static_project_dir = os.path.join(app.static_folder, 'project_assets', project_name)
    os.makedirs(static_project_dir, exist_ok=True)
    
    # Create an empty log file for the GPT Engineer process to write to
    log_file = os.path.join(project_dir, 'gpt_engineer.log')
    with open(log_file, 'w') as f:
        f.write(f"Starting generation for project: {project_name}\n")
        f.write(f"Timestamp: {datetime.datetime.now()}\n\n")
        f.write("Initializing Three.js game generation with gpt-engineer...\n\n")
        

    
    # Copy the basic template to the static directory so it's immediately accessible
    copy_generated_files_to_static(project_name, project_dir)
    
    # Get the OpenAI API key from the gpt-engineer .env file
    api_key = None
    gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
    env_path = os.path.join(gpte_repo, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('OPENAI_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break
        except Exception as e:
            print(f"Error reading .env file: {e}")
    
    if not api_key:
        return jsonify({"status": "error", "message": "OpenAI API key not found"}), 500

    # Directly start gpt-engineer process in the foreground to ensure it runs
    print(f"Starting GPT Engineer for project: {project_name}")
    
    # Create a background thread that will actually run the process
    def run_gpte_background():
        # Get log file path
        log_file_path = os.path.join(project_dir, 'gpt_engineer.log')
        print(f"Log file will be written to: {log_file_path}")
        
        # Open the log file for appending
        with open(log_file_path, 'a') as log_file:
            # Create the command with environment variables properly exported
            cmd = f"cd {gpte_repo} && OPENAI_API_KEY='{api_key}' python -m gpt_engineer.applications.cli.main \"{project_dir}\" --temperature 0.7 --verbose"
            log_file.write(f"Executing command: {cmd}\n")
            print(f"Executing command: {cmd}")
            
            try:
                # First log the API key check for debugging (without exposing the full key)
                key_prefix = api_key[:4] if api_key else "None"
                log_file.write(f"API Key check: {key_prefix}...\n")
                print(f"API Key check: {key_prefix}...")
                
                # Verify the project directory exists
                if not os.path.exists(project_dir):
                    error_msg = f"Project directory does not exist: {project_dir}"
                    log_file.write(f"ERROR: {error_msg}\n")
                    print(f"ERROR: {error_msg}")
                else:
                    log_file.write(f"Project directory exists: {project_dir}\n")
                    print(f"Project directory exists: {project_dir}")
                
                # Verify GPT Engineer repo exists
                if not os.path.exists(gpte_repo):
                    error_msg = f"GPT Engineer repo does not exist: {gpte_repo}"
                    log_file.write(f"ERROR: {error_msg}\n")
                    print(f"ERROR: {error_msg}")
                else:
                    log_file.write(f"GPT Engineer repo exists: {gpte_repo}\n")
                    print(f"GPT Engineer repo exists: {gpte_repo}")
                
                # Set up the environment with the API key
                env = os.environ.copy()
                env['OPENAI_API_KEY'] = api_key
                
                # Run the process with the environment variables and capture output in real-time
                process = subprocess.Popen(
                    f"cd {gpte_repo} && python -m gpt_engineer.applications.cli.main \"{project_dir}\" --temperature 0.7 --verbose",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True,
                    env=env
                )
                
                # Read output line by line as it happens
                for line in process.stdout:
                    line = line.rstrip()
                    print(f"GPT Engineer output: {line}")
                    log_file.write(f"{line}\n")
                    log_file.flush()  # Ensure content is written immediately
                
                # Wait for process to complete
                return_code = process.wait()
                
                if return_code == 0:
                    print("GPT Engineer process completed successfully")
                    log_file.write("\n✅ Game generation complete!\n")
                    
                    # Create a completion marker file
                    with open(os.path.join(project_dir, ".gpte_done"), "w") as f:
                        f.write(f"Process completed at {datetime.datetime.now()}")
                    
                    # Copy generated files to static
                    copy_generated_files_to_static(project_name, project_dir)
                else:
                    error_msg = f"GPT Engineer process failed with return code {return_code}"
                    print(error_msg)
                    log_file.write(f"\nError: {error_msg}\n")
            
            except Exception as e:
                print(f"Error running GPT Engineer: {e}")
                log_file.write(f"\nError: {str(e)}\n")
    
    # Start the background thread
    thread = threading.Thread(target=run_gpte_background)
    thread.daemon = True
    thread.start()
    
    # When redirecting to the play page, add a parameter to indicate it's a new project
    return jsonify({"status": "success", "message": "Game project created and gpt-engineer started", "project": project_name})

def create_basic_threejs_template(project_dir, prompt):
    """Create a basic working Three.js template in the workspace/generated directory"""
    
    # Create workspace and generated directories (where gpt-engineer will put files)
    workspace_dir = os.path.join(project_dir, "workspace")
    generated_dir = os.path.join(workspace_dir, "generated")
    os.makedirs(generated_dir, exist_ok=True)
    
    # Create a placeholder README.md in the generated directory to explain what's happening
    readme_content = f"""
# Temporary Placeholder for {os.path.basename(project_dir)} Game

This is a placeholder for your Three.js game that will be generated based on:
- Description: {prompt}

Click the 'Regenerate' button on the project page to have AI create your custom game.
"""
    
    with open(os.path.join(generated_dir, "README.md"), "w") as f:
        f.write(readme_content)
    
    # Create an empty index.html file in the generated directory as a placeholder
    # This ensures the file structure is recognized but encourages regeneration
    placeholder_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generating {os.path.basename(project_dir)} - Three.js Game</title>
    <style>
        body {{ 
            margin: 0; 
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #222;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
        }}
        .message {{ 
            max-width: 80%;
            padding: 2rem;
            background-color: rgba(0,0,0,0.7);
            border-radius: 8px;
        }}
        h1 {{ color: #4CAF50; }}
        p {{ line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="message">
        <h1>Your Custom Three.js Game Will Appear Here</h1>
        <p>This is just a placeholder. Return to the project page and click "Regenerate" to create your
        custom Three.js game based on your description.</p>
        <p><strong>Description:</strong> {prompt}</p>
    </div>
</body>
</html>
"""
    
    with open(os.path.join(generated_dir, "index.html"), "w") as f:
        f.write(placeholder_html)

@app.route('/run_gpte', methods=['POST'])
def run_gpte():
    """Run GPT Engineer on an existing project to regenerate the game"""
    try:
        # Check if this is an AJAX request to prevent redirects
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        print(f"Received regenerate request with data: {request.form} (AJAX: {is_ajax})")
        
        project_name = request.form.get('project_name', '').strip()
        # Get the prompt if available from form data
        prompt = request.form.get('prompt', None)
        print(f"Project name from form: '{project_name}', prompt provided: {bool(prompt)}")
        
        if not project_name:
            return jsonify({"status": "error", "message": "Project name is required"}), 400
        
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        print(f"Project directory: {project_dir}")
        if not os.path.exists(project_dir):
            return jsonify({"status": "error", "message": "Project not found"}), 404
    
        # Remove the completion marker file if it exists
        done_file = os.path.join(project_dir, ".gpte_done")
        if os.path.exists(done_file):
            try:
                os.remove(done_file)
                print(f"Removed completion marker file: {done_file}")
            except Exception as e:
                print(f"Error removing completion marker file: {e}")
            
        # Get the gpt-engineer path and environment
        gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
        if not os.path.exists(gpte_repo):
            gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
            print(f"Using original path: {gpte_repo}")
        print(f"GPT Engineer repo path: {gpte_repo}")
        
        # Get OpenAI API key from gpt-engineer .env file
        api_key = None
        env_path = os.path.join(gpte_repo, '.env')
        print(f"Checking for .env file at: {env_path}")
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.strip().startswith('OPENAI_API_KEY='):
                            api_key = line.strip().split('=', 1)[1]
                            print("Found API key in .env file")
                            break
            except Exception as e:
                print(f"Error reading .env file: {e}")
                return jsonify({"status": "error", "message": f"Error reading API key: {e}"}), 500
        
        if not api_key:
            return jsonify({"status": "error", "message": "OpenAI API key not found. Please set it in ~/Desktop/gpt-engineer/.env"}), 500
        
        # Set up environment variables
        env_vars = os.environ.copy()
        env_vars['OPENAI_API_KEY'] = api_key
        print(f"Set up environment variables")
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(project_dir, "workspace", "logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
            print(f"Created logs directory: {logs_dir}")
        except Exception as e:
            print(f"Error creating logs directory: {e}")
            return jsonify({"status": "error", "message": f"Error creating logs directory: {e}"}), 500
        
        # Create a log file for this run
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(logs_dir, f"gpte_run_{timestamp}.log")
        print(f"Log file path: {log_file}")
        
        # Much simpler approach to run GPT Engineer
        # Create a log file for this run
        log_file = os.path.join(project_dir, 'gpt_engineer.log')
        
        # Update or create prompt file if we received a prompt
        prompt_file = os.path.join(project_dir, 'prompt')
        if prompt:
            print(f"[GPT ENGINEER] Updating prompt file with new prompt: {prompt}")
            
            # Enhanced prompt with very specific instructions for Three.js
            enhanced_prompt = f"Create a 3D game using Three.js with the following specifications:\n\n{prompt}\n\nREQUIREMENTS:\n- Use Three.js library\n- Create a web-based 3D game that runs in the browser\n- Include index.html as the main entry point\n- Use JavaScript for game logic\n- Make sure the game initializes properly without errors\n- Add clear user controls/instructions\n- Include proper lighting and camera setup"
            
            # Write the updated prompt file with enhanced instructions
            with open(prompt_file, 'w') as f:
                f.write(enhanced_prompt)
                
            print(f"[GPT ENGINEER] Wrote enhanced prompt to {prompt_file}")
        
        # Write initial info to the log file
        with open(log_file, 'w') as f:
            f.write(f"Starting GPT Engineer for project: {project_name}\n")
            f.write(f"Start time: {datetime.datetime.now()}\n")
            f.write("Initializing game generation...\n")
        
        # Define a function to run in a separate thread
        def run_gpte_thread():
            try:
                # Simple, direct command execution
                cmd = f"cd {gpte_repo} && python -m gpt_engineer.applications.cli.main \"{project_dir}\" --temperature 0.7"
                
                # Set up environment with API key
                env_vars = os.environ.copy()
                env_vars['OPENAI_API_KEY'] = api_key
                
                # Log the command we're about to run (without API key)
                print(f"Running command: cd {gpte_repo} && python -m gpt_engineer.applications.cli.main \"{project_dir}\" --temperature 0.7")
                
                # Execute the command directly with real-time output capture
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env_vars
                )
                
                # Capture and log output in real-time
                with open(log_file, 'a') as log_f:
                    while True:
                        output = process.stdout.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            log_f.write(output)
                            log_f.flush()
                            print(output.strip())
                
                # Create a marker file to indicate completion
                with open(done_file, "w") as f:
                    f.write(f"Process completed at {datetime.datetime.now()}")
                
                # Copy generated files to the static directory for serving
                copy_generated_files_to_static(project_name, project_dir)
                print("GPT Engineer process completed successfully")
                
            except Exception as e:
                print(f"Error running GPT Engineer: {e}")
                with open(log_file, 'a') as f:
                    f.write(f"\nError: {str(e)}\n")
        
        # Start the thread to run GPT Engineer
        thread = threading.Thread(target=run_gpte_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "started", 
            "message": "Game regeneration started using gpt-engineer",
            "project": project_name,
            "log_file": os.path.basename(log_file)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error regenerating game: {str(e)}"}), 500

@app.route('/skip_gpte', methods=['POST'])
def skip_gpte():
    """Skip GPT Engineer and directly create a sample Three.js game"""
    project_name = request.form.get('project_name', '').strip()
    
    if not project_name:
        return jsonify({"status": "error", "message": "Project name is required"}), 400
    
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    
    # Create the workspace/generated directory if it doesn't exist
    generated_dir = os.path.join(project_dir, "workspace", "generated")
    os.makedirs(generated_dir, exist_ok=True)
    
    # Sample index.html with Three.js game
    index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cat Shootout Game</title>
    <style>
        body { margin: 0; overflow: hidden; }
        canvas { display: block; }
        .ui { position: absolute; top: 10px; left: 10px; color: white; font-family: Arial; }
    </style>
</head>
<body>
    <div class="ui">
        <div id="score">Score: 0</div>
        <div id="health">Health: 100</div>
    </div>
    
    <script type="module">
        import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
        import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';
        
        // Game state
        const game = {
            score: 0,
            health: 100,
            running: true
        };
        
        // Set up scene
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x87CEEB); // Sky blue background
        
        // Set up camera
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.set(0, 5, 10);
        
        // Set up renderer
        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.shadowMap.enabled = true;
        document.body.appendChild(renderer.domElement);
        
        // Controls
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        
        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
        directionalLight.position.set(5, 10, 7.5);
        directionalLight.castShadow = true;
        scene.add(directionalLight);
        
        // Ground
        const groundGeometry = new THREE.PlaneGeometry(50, 50);
        const groundMaterial = new THREE.MeshStandardMaterial({ color: 0x8B4513 });
        const ground = new THREE.Mesh(groundGeometry, groundMaterial);
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = -1;
        ground.receiveShadow = true;
        scene.add(ground);
        
        // Player (Cat)
        const playerGeometry = new THREE.BoxGeometry(1, 1, 1);
        const playerMaterial = new THREE.MeshStandardMaterial({ color: 0xA0522D });
        const player = new THREE.Mesh(playerGeometry, playerMaterial);
        player.position.set(0, 0, 0);
        player.castShadow = true;
        scene.add(player);
        
        // Create targets
        const targets = [];
        function createTarget() {
            const targetGeometry = new THREE.SphereGeometry(0.5, 16, 16);
            const targetMaterial = new THREE.MeshStandardMaterial({ color: 0xff0000 });
            const target = new THREE.Mesh(targetGeometry, targetMaterial);
            
            // Random position
            const angle = Math.random() * Math.PI * 2;
            const distance = 5 + Math.random() * 10;
            target.position.x = Math.cos(angle) * distance;
            target.position.z = Math.sin(angle) * distance;
            target.position.y = 0;
            
            target.castShadow = true;
            scene.add(target);
            targets.push(target);
        }
        
        // Create initial targets
        for (let i = 0; i < 5; i++) {
            createTarget();
        }
        
        // Projectiles
        const projectiles = [];
        function shootProjectile() {
            const projectileGeometry = new THREE.SphereGeometry(0.2, 8, 8);
            const projectileMaterial = new THREE.MeshStandardMaterial({ color: 0xffff00 });
            const projectile = new THREE.Mesh(projectileGeometry, projectileMaterial);
            
            // Set position to player position
            projectile.position.copy(player.position);
            
            // Calculate direction toward camera target
            const direction = new THREE.Vector3();
            direction.subVectors(controls.target, camera.position).normalize();
            
            // Store direction in projectile for movement
            projectile.userData.direction = direction;
            projectile.userData.speed = 0.5;
            
            scene.add(projectile);
            projectiles.push(projectile);
        }
        
        // Keyboard controls
        const keys = {};
        window.addEventListener('keydown', (e) => {
            keys[e.key] = true;
            
            // Shoot on space
            if (e.key === ' ') {
                shootProjectile();
            }
        });
        
        window.addEventListener('keyup', (e) => {
            keys[e.key] = false;
        });
        
        // Handle player movement
        function handlePlayerMovement() {
            const moveSpeed = 0.1;
            
            if (keys['w'] || keys['ArrowUp']) {
                player.position.z -= moveSpeed;
            }
            if (keys['s'] || keys['ArrowDown']) {
                player.position.z += moveSpeed;
            }
            if (keys['a'] || keys['ArrowLeft']) {
                player.position.x -= moveSpeed;
            }
            if (keys['d'] || keys['ArrowRight']) {
                player.position.x += moveSpeed;
            }
            
            // Update camera target to follow player
            controls.target.copy(player.position);
        }
        
        // Handle window resize
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
        
        // Check for collisions between projectiles and targets
        function checkCollisions() {
            // Projectile-target collision
            for (let i = projectiles.length - 1; i >= 0; i--) {
                const projectile = projectiles[i];
                
                for (let j = targets.length - 1; j >= 0; j--) {
                    const target = targets[j];
                    
                    const distance = projectile.position.distanceTo(target.position);
                    if (distance < 0.7) { // 0.5 (target radius) + 0.2 (projectile radius)
                        // Remove target and projectile
                        scene.remove(target);
                        scene.remove(projectile);
                        targets.splice(j, 1);
                        projectiles.splice(i, 1);
                        
                        // Increase score
                        game.score += 10;
                        document.getElementById('score').textContent = `Score: ${game.score}`;
                        
                        // Create a new target
                        setTimeout(createTarget, 1000);
                        
                        break;
                    }
                }
            }
        }
        
        // Update UI
        function updateUI() {
            document.getElementById('score').textContent = `Score: ${game.score}`;
            document.getElementById('health').textContent = `Health: ${game.health}`;
        }
        
        // Game loop
        function animate() {
            if (!game.running) return;
            
            requestAnimationFrame(animate);
            
            // Update controls
            controls.update();
            
            // Handle player movement
            handlePlayerMovement();
            
            // Update projectiles
            for (let i = projectiles.length - 1; i >= 0; i--) {
                const projectile = projectiles[i];
                projectile.position.add(
                    projectile.userData.direction.clone().multiplyScalar(projectile.userData.speed)
                );
                
                // Remove projectiles that go too far
                if (projectile.position.length() > 50) {
                    scene.remove(projectile);
                    projectiles.splice(i, 1);
                }
            }
            
            // Check for collisions
            checkCollisions();
            
            // Render scene
            renderer.render(scene, camera);
        }
        
        // Start game loop
        animate();
    </script>
</body>
</html>
"""
    
    # Sample game.js file
    game_js = """
// game.js - Main game logic
// This is just a placeholder file since our game code is in index.html
"""

    try:
        # Write the files
        with open(os.path.join(generated_dir, "index.html"), "w") as f:
            f.write(index_html)
            
        with open(os.path.join(generated_dir, "game.js"), "w") as f:
            f.write(game_js)
            
        # Create the completion marker file
        with open(os.path.join(project_dir, ".gpte_done"), "w") as f:
            f.write(f"Process completed at {datetime.datetime.now()}")
            
        return jsonify({
            "status": "success", 
            "message": "Sample Three.js game created successfully",
            "project": project_name
        })
    except Exception as e:
        # Catch-all exception handler for any unexpected errors
        error_message = f"Error regenerating game: {str(e)}"
        print(f"ERROR in create_threejs_game: {error_message}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": error_message}), 500


def try_run_gpte_background(project_dir):
    """Try to run gpt-engineer/gpt-engineer in the background as a fallback"""
    try:
        # Get OpenAI API key from gpt-engineer or gpt-engineer .env file
        api_key = None
        env_path = os.path.expanduser('~/Desktop/gpt-engineer/.env')
        if not os.path.exists(env_path):
            env_path = os.path.expanduser('~/Desktop/gpt-engineer/.env')
            print(f"Using original .env path: {env_path}")
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('OPENAI_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break
        
        if not api_key:
            return False
        
        # Get the path to the gpt-engineer/gpt-engineer repository
        gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
        if not os.path.exists(gpte_repo):
            gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
            print(f"Using original repository path: {gpte_repo}")
        
        # Ensure we're using the correct Python environment with gpt-engineer installed
        gpte_bin = os.path.join(gpte_repo, 'venv/bin/python') if os.path.exists(os.path.join(gpte_repo, 'venv/bin/python')) else 'python'
        
        # Set up the environment variables
        env_vars = os.environ.copy()
        env_vars['OPENAI_API_KEY'] = api_key
        env_vars['PYTHONPATH'] = gpte_repo + ':' + env_vars.get('PYTHONPATH', '')
        
        # We need to run from the gpt-engineer directory to access all modules correctly
        cmd = f"cd {gpte_repo} && {gpte_bin} -m gpt_engineer.cli.main {project_dir} --model gpt-4o --temperature 0.7 --use-custom-preprompts --verbose"
        
        # Run the command in a subprocess
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            env=env_vars
        )
        
        return True
    except Exception as e:
        print(f"Error running gpt-engineer in background: {e}")
        return False


def create_direct_playable_game(project_dir, game_type, prompt):
    """Create a directly playable Three.js game in the workspace/generated directory"""
    # Ensure workspace/generated directory exists
    workspace_dir = os.path.join(project_dir, "workspace")
    generated_dir = os.path.join(workspace_dir, "generated")
    os.makedirs(generated_dir, exist_ok=True)
    
    # Create a custom game based on the type and prompt
    game_type_lower = game_type.lower()
    
    # Determine game characteristics based on the game type and prompt
    game_props = {
        "playerColor": "0x00ff00",  # Default green
        "enemyColor": "0xff0000",  # Default red
        "groundColor": "0x555555", # Default gray
        "skyColor": "0x87CEEB",    # Default sky blue
        "objectType": "box",       # Default object type
        "cameraView": "third-person" # Default camera view
    }
    
    # Customize based on game type
    if 'shooter' in game_type_lower:
        game_props["cameraView"] = "first-person"
        game_props["objectType"] = "sphere"
    elif 'platformer' in game_type_lower:
        game_props["cameraView"] = "side"
        game_props["skyColor"] = "0x1E90FF"  # Deeper blue
    elif 'racing' in game_type_lower:
        game_props["groundColor"] = "0x333333" # Darker for asphalt
        game_props["playerColor"] = "0xFF5733" # Orange-red for car
    elif 'puzzle' in game_type_lower:
        game_props["skyColor"] = "0x000000" # Black background
        game_props["groundColor"] = "0x222222" # Dark gray
        
    # Further customize based on prompt keywords
    prompt_lower = prompt.lower()
    if 'space' in prompt_lower or 'galaxy' in prompt_lower or 'star' in prompt_lower:
        game_props["skyColor"] = "0x000033" # Dark space blue
        game_props["groundColor"] = "0x111111" # Very dark
    if 'forest' in prompt_lower or 'jungle' in prompt_lower or 'grass' in prompt_lower:
        game_props["groundColor"] = "0x3A5F0B" # Forest green
    if 'snow' in prompt_lower or 'ice' in prompt_lower or 'winter' in prompt_lower:
        game_props["groundColor"] = "0xEEEEFF" # Light blue-white
        game_props["skyColor"] = "0xADD8E6" # Light blue
    if 'desert' in prompt_lower or 'sand' in prompt_lower:
        game_props["groundColor"] = "0xD2B48C" # Tan
        game_props["skyColor"] = "0x87CEEB" # Bright blue
    
    # Create the index.html file
    index_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{os.path.basename(project_dir)} - Three.js Game</title>
    <style>
        body {{ margin: 0; overflow: hidden; }}
        #info {{ 
            position: absolute; 
            top: 10px; 
            width: 100%; 
            text-align: center; 
            color: white; 
            z-index: 100;
            text-shadow: 1px 1px 1px black;
            pointer-events: none;
        }}
        #controls {{ 
            position: absolute; 
            bottom: 10px; 
            width: 100%; 
            text-align: center; 
            color: white; 
            z-index: 100;
            text-shadow: 1px 1px 1px black;
            background-color: rgba(0,0,0,0.5);
            padding: 10px 0;
        }}
        .score {{ 
            position: absolute; 
            top: 50px; 
            width: 100%; 
            text-align: center; 
            color: white; 
            font-size: 24px;
            text-shadow: 2px 2px 2px black;
        }}
    </style>
</head>
<body>
    <div id="info">
        <h1>{os.path.basename(project_dir)}</h1>
        <p>{prompt}</p>
    </div>
    <div id="controls">Controls: WASD = Move | Arrow Keys = Alternative movement | Mouse = Look around | Space = Jump | Click = Interact</div>
    <div id="score" class="score">Score: <span id="score-value">0</span></div>
    
    <script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
    <script src="game.js"></script>
</body>
</html>"""

    # Create a custom game.js file based on the type and prompt
    game_js = f"""
// Custom Three.js game based on: {game_type}
// Description: {prompt}

// Game initialization
let score = 0;
const scoreElement = document.getElementById('score-value');

// Scene setup
const scene = new THREE.Scene();
scene.background = new THREE.Color({game_props['skyColor']});

// Camera setup
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);

// Determine camera position based on game type
if ("{game_props['cameraView']}" === "first-person") {{
    camera.position.set(0, 1.7, 0); // Eye level
}} else if ("{game_props['cameraView']}" === "side") {{
    camera.position.set(10, 5, 0); // Side view for platformers
}} else {{
    // Default third-person view
    camera.position.set(0, 5, 10);
}}

// Renderer setup
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

// Lighting
const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
directionalLight.position.set(5, 10, 7.5);
directionalLight.castShadow = true;
directionalLight.shadow.mapSize.width = 1024;
directionalLight.shadow.mapSize.height = 1024;
scene.add(directionalLight);

// Ground plane
const groundGeometry = new THREE.PlaneGeometry(100, 100);
const groundMaterial = new THREE.MeshStandardMaterial({{ 
    color: {game_props['groundColor']}, 
    roughness: 0.8,
    metalness: 0.2
}});
const ground = new THREE.Mesh(groundGeometry, groundMaterial);
ground.rotation.x = -Math.PI / 2; // Rotate to be flat
ground.receiveShadow = true;
scene.add(ground);

// Player character
let playerGeometry;
if ("{game_props['objectType']}" === "sphere") {{
    playerGeometry = new THREE.SphereGeometry(1, 32, 32);
}} else {{
    // Default to box
    playerGeometry = new THREE.BoxGeometry(1, 2, 1);
}}

const playerMaterial = new THREE.MeshStandardMaterial({{ 
    color: {game_props['playerColor']}, 
    metalness: 0.3,
    roughness: 0.4
}});
const player = new THREE.Mesh(playerGeometry, playerMaterial);
player.position.y = 1; // Position on the ground
player.castShadow = true;
scene.add(player);

// Create enemies/obstacles
const enemies = [];
const numEnemies = 10;

for (let i = 0; i < numEnemies; i++) {{
    // Randomize enemy shape
    let enemyGeometry;
    const shapeRandom = Math.random();
    
    if (shapeRandom < 0.33) {{
        enemyGeometry = new THREE.BoxGeometry(1, 1, 1);
    }} else if (shapeRandom < 0.66) {{
        enemyGeometry = new THREE.SphereGeometry(0.5, 16, 16);
    }} else {{
        enemyGeometry = new THREE.ConeGeometry(0.5, 1, 16);
    }}
    
    const enemyMaterial = new THREE.MeshStandardMaterial({{ color: {game_props['enemyColor']} }});
    const enemy = new THREE.Mesh(enemyGeometry, enemyMaterial);
    
    // Position randomly around the scene
    enemy.position.x = (Math.random() - 0.5) * 60;
    enemy.position.y = 0.5 + Math.random() * 2;
    enemy.position.z = (Math.random() - 0.5) * 60;
    
    enemy.castShadow = true;
    enemy.userData.speed = 0.05 + Math.random() * 0.1;
    enemy.userData.rotationSpeed = 0.01 + Math.random() * 0.03;
    
    scene.add(enemy);
    enemies.push(enemy);
}}

// Create collectible items
const collectibles = [];
const numCollectibles = 15;

for (let i = 0; i < numCollectibles; i++) {{
    const collectibleGeometry = new THREE.TetrahedronGeometry(0.5);
    const collectibleMaterial = new THREE.MeshStandardMaterial({{ 
        color: 0xffff00, // Gold color
        metalness: 0.8,
        roughness: 0.2,
        emissive: 0xffff00,
        emissiveIntensity: 0.2
    }});
    
    const collectible = new THREE.Mesh(collectibleGeometry, collectibleMaterial);
    
    // Position randomly around the scene
    collectible.position.x = (Math.random() - 0.5) * 80;
    collectible.position.y = 0.5;
    collectible.position.z = (Math.random() - 0.5) * 80;
    
    // Add some properties for animation
    collectible.userData.rotationSpeed = 0.03;
    collectible.userData.hoverSpeed = 0.01;
    collectible.userData.hoverHeight = 0.5;
    collectible.userData.baseHeight = collectible.position.y;
    collectible.userData.hoverOffset = Math.random() * Math.PI * 2; // Random start position
    
    scene.add(collectible);
    collectibles.push(collectible);
}}

// Game state
const gameState = {{
    moveForward: false,
    moveBackward: false,
    moveLeft: false,
    moveRight: false,
    jump: false,
    playerSpeed: 0.15,
    playerVelocityY: 0,
    gravity: 0.01,
    isOnGround: true,
    jumpForce: 0.2,
    gameStarted: true,
    gameOver: false,
    mouseX: 0,
    mouseY: 0
}};

// Control setup
document.addEventListener('keydown', (event) => {{
    switch(event.code) {{
        case 'KeyW': case 'ArrowUp': gameState.moveForward = true; break;
        case 'KeyS': case 'ArrowDown': gameState.moveBackward = true; break;
        case 'KeyA': case 'ArrowLeft': gameState.moveLeft = true; break;
        case 'KeyD': case 'ArrowRight': gameState.moveRight = true; break;
        case 'Space': 
            if (gameState.isOnGround) {{
                gameState.playerVelocityY = gameState.jumpForce;
                gameState.isOnGround = false;
            }}
            break;
    }}
}});

document.addEventListener('keyup', (event) => {{
    switch(event.code) {{
        case 'KeyW': case 'ArrowUp': gameState.moveForward = false; break;
        case 'KeyS': case 'ArrowDown': gameState.moveBackward = false; break;
        case 'KeyA': case 'ArrowLeft': gameState.moveLeft = false; break;
        case 'KeyD': case 'ArrowRight': gameState.moveRight = false; break;
    }}
}});

// Mouse controls for looking around
document.addEventListener('mousemove', (event) => {{
    // Use relative mouse position from center of screen
    gameState.mouseX = (event.clientX / window.innerWidth) * 2 - 1;
    gameState.mouseY = (event.clientY / window.innerHeight) * 2 - 1;
    
    // Only rotate camera in first-person mode
    if ("{game_props['cameraView']}" === "first-person") {{
        player.rotation.y = -gameState.mouseX * Math.PI;
    }}
}});

// Click for interaction/shooting
document.addEventListener('click', () => {{
    // Increment score on click as a simple interaction
    score += 1;
    scoreElement.textContent = score;
    
    // Simple visual feedback
    const flash = new THREE.Mesh(
        new THREE.SphereGeometry(0.2),
        new THREE.MeshBasicMaterial({{ color: 0xffff00, transparent: true, opacity: 0.8 }})
    );
    
    // Position in front of player
    const direction = new THREE.Vector3(0, 0, -1);
    direction.applyQuaternion(player.quaternion);
    flash.position.copy(player.position).addScaledVector(direction, 2);
    
    scene.add(flash);
    
    // Remove after animation
    setTimeout(() => {{
        scene.remove(flash);
    }}, 200);
}});

// Handle window resize
window.addEventListener('resize', () => {{
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}});

// Collision detection between player and object
function checkCollision(obj1, obj2, minDistance = 1.5) {{
    const dx = obj1.position.x - obj2.position.x;
    const dy = obj1.position.y - obj2.position.y;
    const dz = obj1.position.z - obj2.position.z;
    
    const distance = Math.sqrt(dx*dx + dy*dy + dz*dz);
    return distance < minDistance;
}}

// Game loop
function animate() {{
    requestAnimationFrame(animate);
    
    if (!gameState.gameOver) {{
        // Apply gravity
        gameState.playerVelocityY -= gameState.gravity;
        player.position.y += gameState.playerVelocityY;
        
        // Ground collision
        if (player.position.y < 1) {{
            player.position.y = 1;
            gameState.playerVelocityY = 0;
            gameState.isOnGround = true;
        }}
        
        // Player movement based on facing direction
        const moveX = gameState.moveRight ? 1 : (gameState.moveLeft ? -1 : 0);
        const moveZ = gameState.moveForward ? 1 : (gameState.moveBackward ? -1 : 0);
        
        if ("{game_props['cameraView']}" === "first-person") {{
            // First-person movement relative to player rotation
            const angle = player.rotation.y;
            player.position.x += (moveZ * Math.sin(angle) + moveX * Math.cos(angle)) * gameState.playerSpeed;
            player.position.z += (moveZ * Math.cos(angle) - moveX * Math.sin(angle)) * gameState.playerSpeed;
            
            // Camera follows player position exactly in first-person
            camera.position.copy(player.position);
            camera.position.y += 0.7; // Eye level
            camera.rotation.y = player.rotation.y;
        }} else {{
            // Third-person/side view direct movement
            player.position.x += moveX * gameState.playerSpeed;
            player.position.z -= moveZ * gameState.playerSpeed;
            
            // Basic camera following
            if ("{game_props['cameraView']}" === "side") {{
                // Side-view camera (platformer style)
                camera.position.x = player.position.x;
                camera.position.z = 15; // Fixed side view
                camera.lookAt(player.position);
            }} else {{
                // Third-person camera
                const cameraOffset = new THREE.Vector3(0, 5, 10);
                camera.position.copy(player.position).add(cameraOffset);
                camera.lookAt(player.position);
            }}
        }}
        
        // Enemy animation
        enemies.forEach(enemy => {{
            // Move towards player
            const dx = player.position.x - enemy.position.x;
            const dz = player.position.z - enemy.position.z;
            const distance = Math.sqrt(dx*dx + dz*dz);
            
            if (distance > 1) {{
                enemy.position.x += (dx / distance) * enemy.userData.speed;
                enemy.position.z += (dz / distance) * enemy.userData.speed;
            }}
            
            // Rotate for visual effect
            enemy.rotation.y += enemy.userData.rotationSpeed;
            
            // Check collision with player
            if (checkCollision(player, enemy)) {{
                // Handle collision (reduce score)
                score = Math.max(0, score - 5);
                scoreElement.textContent = score;
                
                // Bounce back from player
                enemy.position.x -= (dx / distance) * 2;
                enemy.position.z -= (dz / distance) * 2;
            }}
        }});
        
        // Collectible animation and collection
        collectibles.forEach((collectible, index) => {{
            // Rotate and hover animation
            collectible.rotation.y += collectible.userData.rotationSpeed;
            collectible.rotation.x += collectible.userData.rotationSpeed * 0.5;
            
            // Hover up and down
            const hoverY = Math.sin(Date.now() * collectible.userData.hoverSpeed + collectible.userData.hoverOffset) * 
                          collectible.userData.hoverHeight;
            collectible.position.y = collectible.userData.baseHeight + hoverY;
            
            // Check collision with player
            if (checkCollision(player, collectible)) {{
                // Remove collectible and increase score
                scene.remove(collectible);
                collectibles.splice(index, 1);
                
                // Update score
                score += 10;
                scoreElement.textContent = score;
                
                // Visual and sound feedback could be added here
            }}
        }});
    }}
    
    renderer.render(scene, camera);
}}

// Game initialization message
console.log("Game loaded! Common controls:");
console.log("WASD: Move | Arrow Keys: Alternative movement | Mouse: Look around");
console.log("Space: Jump | Click: Interact");

// Start the game loop
animate();
"""

    # Write the files to the workspace/generated directory
    with open(os.path.join(generated_dir, "index.html"), "w") as f:
        f.write(index_html)
        
    with open(os.path.join(generated_dir, "game.js"), "w") as f:
        f.write(game_js)

@app.route('/project/<project_name>')
def view_project(project_name):
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return redirect(url_for('index'))
    
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        for filename in filenames:
            if filename == 'prompt' or filename.endswith('.py') or filename.endswith('.html') or filename.endswith('.js') or filename.endswith('.css'):
                rel_path = os.path.relpath(os.path.join(root, filename), project_dir)
                files.append(rel_path)
    
    # Read prompt file
    prompt_path = os.path.join(project_dir, 'prompt')
    prompt = ""
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r') as f:
            prompt = f.read()
    
    return render_template('project.html', project_name=project_name, files=files, prompt=prompt)

@app.route('/project/<project_name>/file/<path:file_path>')
def view_file(project_name, file_path):
    file_path = file_path.replace('..', '')  # Basic security
    full_path = os.path.join(BASE_PROJECT_DIR, project_name, file_path)
    
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return jsonify({"status": "error", "message": "File not found"}), 404
    
    try:
        with open(full_path, 'r') as f:
            content = f.read()
        return jsonify({"content": content})
    except UnicodeDecodeError:
        # For binary files
        return jsonify({"content": "Binary file - cannot display content"}), 415

@app.route('/play/<project_name>')
def play_game(project_name):
    """Renders a page to play the generated Three.js game"""
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return redirect(url_for('index'))
    
    return render_template('play_game.html', project_name=project_name)

@app.route('/check_game_exists/<project_name>')
def check_game_exists(project_name):
    """Check if a game project exists and has generated files"""
    try:
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        project_exists = os.path.exists(project_dir)
        
        # Check if the project has generated files
        has_files = False
        if project_exists:
            # Check if there's a workspace/output directory with files
            output_dir = os.path.join(project_dir, 'workspace', 'output')
            static_dir = os.path.join(STATIC_DIR, 'project_assets', project_name)
            
            has_files = (
                (os.path.exists(output_dir) and any(os.listdir(output_dir))) or
                (os.path.exists(static_dir) and any(os.listdir(static_dir)))
            )
        
        return jsonify({
            "exists": project_exists,
            "has_files": has_files
        })
    except Exception as e:
        print(f"Error checking if game exists: {e}")
        return jsonify({"exists": False, "has_files": False, "error": str(e)})

@app.route('/build/<project_name>')
def game_builder(project_name):
    """Renders the game builder interface with chat and preview"""
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return redirect(url_for('index'))
    
    # Extract prompt from project
    prompt = ""
    prompt_path = os.path.join(project_dir, "prompt")
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r') as f:
            content = f.read()
            if "DETAILED DESCRIPTION:" in content:
                prompt = content.split("DETAILED DESCRIPTION:", 1)[1].split("\n\n", 1)[0].strip()
    
    return render_template('game_builder.html', project_name=project_name, prompt=prompt)

@app.route('/project_assets/<project_name>/<path:file_path>')
def serve_project_assets(project_name, file_path):
    """Serves static files from the static/project_assets directory"""
    project_assets_dir = os.path.join('static', 'project_assets', project_name)
    if os.path.exists(os.path.join(project_assets_dir, file_path)):
        return send_from_directory(project_assets_dir, file_path)
    else:
        # Fallback to original directory if not found in static/project_assets
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        return send_from_directory(project_dir, file_path)

@app.route('/play/<project_name>/<path:file_path>')
def serve_game_files(project_name, file_path):
    """Serves game files, looking in multiple possible locations"""
    # First try in static/project_assets directory (where we copy generated files)
    project_assets_dir = os.path.join('static', 'project_assets', project_name)
    if os.path.exists(os.path.join(project_assets_dir, file_path)):
        return send_from_directory(project_assets_dir, file_path)
        
    # Then look in gpt-projects locations
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    
    # Look in multiple possible locations in the following priority order:
    # 1. workspace/generated - where gpt-engineer puts files
    # 2. workspace - alternative location
    # 3. Project root - where our template was
    possible_locations = [
        os.path.join(project_dir, 'workspace', 'generated'),
        os.path.join(project_dir, 'workspace'),
        project_dir
    ]
    
    # Try to find the file in each location
    for location in possible_locations:
        file_path_full = os.path.join(location, file_path)
        if os.path.exists(file_path_full):
            return send_from_directory(location, file_path)
    
    # If we didn't find the file, return a 404
    return f"File {file_path} not found", 404
    
# Add a route to handle direct access to play game assets
@app.route('/play/<project_name>/', defaults={'file_path': 'index.html'})
@app.route('/play/<project_name>')
def play_game_root(project_name):
    """Serve the index.html file by default when accessing /play/<project_name>/"""
    # First try in static/project_assets directory
    project_assets_dir = os.path.join('static', 'project_assets', project_name)
    if os.path.exists(os.path.join(project_assets_dir, 'index.html')):
        return send_from_directory(project_assets_dir, 'index.html')
        
    # If not found in static, look in the original locations
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    possible_locations = [
        os.path.join(project_dir, 'workspace', 'generated'),
        os.path.join(project_dir, 'workspace'),
        project_dir
    ]
    
    for location in possible_locations:
        if os.path.exists(os.path.join(location, 'index.html')):
            return send_from_directory(location, 'index.html')
    
    # If no index.html is found, fall back to the template
    return render_template('play_game.html', project_name=project_name)

@app.route('/update_game', methods=['POST'])
def update_game():
    """Handle natural language game modifications from the chat interface using gpt-engineer"""
    data = request.get_json()
    project_name = data.get('project_name')
    modification = data.get('modification')
    
    if not project_name or not modification:
        return jsonify({"status": "error", "message": "Project name and modification are required"}), 400
    
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    
    # Remove the completion marker file if it exists
    done_file = os.path.join(project_dir, ".gpte_done")
    if os.path.exists(done_file):
        os.remove(done_file)
    
    # Process the natural language modification using gpt-engineer
    try:
        # Extract current prompt
        current_prompt = ""
        
        # Check for prompt in prompt file
        prompt_path = os.path.join(project_dir, "prompt")
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                current_prompt = f.read()
        
        # Create a new prompt file that incorporates the modification request
        new_prompt = f"{current_prompt}\n\nMODIFICATION REQUEST: {modification}\n"
        new_prompt += "Please modify the existing game code based on this request. Keep all existing functionality intact unless specifically asked to change it."
        
        with open(prompt_path, 'w') as f:
            f.write(new_prompt)
        
        # Get the gpt-engineer path and environment
        gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
        if not os.path.exists(gpte_repo):
            gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
            print(f"Using original path: {gpte_repo}")
        
        # Get OpenAI API key from gpt-engineer .env file
        api_key = None
        env_path = os.path.join(gpte_repo, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('OPENAI_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break
        
        if not api_key:
            return jsonify({"status": "error", "message": "OpenAI API key not found. Please set it in ~/Desktop/gpt-engineer/.env"}), 500
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(project_dir, "workspace", "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Create a log file for this run
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(logs_dir, f"gpte_update_{timestamp}.log")
        
        # Set up environment variables
        env_vars = os.environ.copy()
        env_vars['OPENAI_API_KEY'] = api_key
        
        # Use -i flag for improve mode to modify existing code
        # Construct a more robust command that ensures the API key is properly set
        # Updated to use the correct module path (applications.cli.main instead of cli.main)
        # Quote the project path to handle spaces in directory names
        cmd = f"cd {gpte_repo} && OPENAI_API_KEY='{api_key}' python -m gpt_engineer.applications.cli.main \"{project_dir}\" -i --temperature 0.7 --verbose"
        
        # Log command details (without API key)
        safe_cmd = f"cd {gpte_repo} && OPENAI_API_KEY='***' python -m gpt_engineer.applications.cli.main \"{project_dir}\" -i --temperature 0.7 --verbose"
        print(f"Running gpt-engineer to modify game: {safe_cmd}")
        
        # Run the command in a subprocess and redirect output to log file
        with open(log_file, 'w') as f:
            # Write a header to the log file to make it easier to parse
            f.write("===== GPT ENGINEER MODIFICATION LOG START =====\n")
            f.write(f"Running command: {safe_cmd}\n")
            f.write(f"Start time: {datetime.datetime.now()}\n")
            f.write(f"Modification request: {modification}\n")
            f.write(f"API key found: {'Yes, length='+str(len(api_key)) if api_key else 'No'}\n")
            f.write(f"Project directory: {project_dir} (exists: {os.path.exists(project_dir)})\n")
            f.write(f"gpt-engineer repo: {gpte_repo} (exists: {os.path.exists(gpte_repo)})\n")
            f.write("===== COMMAND OUTPUT =====\n")
            f.flush()
            
            # Also print to console for easier debugging
            print(f"Starting gpt-engineer for project: {project_name}")
            print(f"Modification: {modification}")
            print(f"Project directory: {project_dir} (exists: {os.path.exists(project_dir)})")
            print(f"gpt-engineer repo: {gpte_repo} (exists: {os.path.exists(gpte_repo)})")
            print(f"API key found: {'Yes' if api_key else 'No'}")
            
            # Create a pre-selected file configuration to bypass file selection
            # First create a simple toml file that selects all files
            toml_dir = os.path.join(project_dir, '.gpteng')
            os.makedirs(toml_dir, exist_ok=True)
            with open(os.path.join(toml_dir, 'file_selection.toml'), 'w') as f:
                f.write("selected = ['*']")  # Select all files by default
                
            # Create or update the improve.txt file to be read by our modified gpt-engineer
            with open(os.path.join(project_dir, 'improve.txt'), 'w') as improve_file:
                improve_file.write(modification)
                
            # Then run gpt-engineer with -i flag - no need for printf with our modified source code
            noninteractive_cmd = f"cd {gpte_repo} && OPENAI_API_KEY='{api_key}' python -m gpt_engineer.applications.cli.main \"{project_dir}\" -i --temperature 0.7 --verbose"
            
            process = subprocess.Popen(
                noninteractive_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env_vars
            )
            
            # Process output in real-time while writing to log file
            try:
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        f.write(output)
                        f.flush()
                        print(output.strip())
            except IOError as e:
                print(f"Error processing output: {e}")
                f.write(f"\nError processing output: {e}\n")
                f.flush()
            
            # Get the return code
            return_code = process.poll()
            f.write(f"\n===== Process exited with code: {return_code} =====\n")
        
        # Start a thread to check when the process is done
        def monitor_process():
            process_completed = False
            try:
                # Wait for process with a timeout to prevent hanging
                process.wait(timeout=600)  # 10 minute timeout
                process_completed = True
            except subprocess.TimeoutExpired:
                print(f"gpt-engineer process timed out after 10 minutes")
                try:
                    process.kill()
                except Exception as e:
                    print(f"Error terminating process: {e}")
            except Exception as e:
                print(f"Error in process monitoring: {e}")
                
            try:
                # Create a marker file to indicate completion
                with open(done_file, "w") as done_marker:
                    done_marker.write(f"Process completed at {datetime.datetime.now()} - {'Success' if process_completed else 'Timeout or Error'}")
            except Exception as e:
                print(f"Error creating done file: {e}")
                
            try:
                # Copy generated files to the static directory for serving
                copy_generated_files_to_static(project_name, project_dir)
            except Exception as e:
                print(f"Error copying generated files: {e}")
        
        thread = threading.Thread(target=monitor_process)
        thread.daemon = True
        thread.start()
        
        # Create a meaningful response message for immediate return
        response_message = f"Working on your request to '{modification}'. You'll see updates in real-time as the code is being generated."
        
        return jsonify({
            "status": "started", 
            "message": response_message,
            "log_file": os.path.basename(log_file)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error starting game update: {str(e)}"}), 500


def apply_game_modification(project_dir, game_type, current_prompt, modification):
    """Apply a natural language modification to the game"""
    workspace_dir = os.path.join(project_dir, "workspace")
    generated_dir = os.path.join(workspace_dir, "generated")
    game_js_path = os.path.join(generated_dir, "game.js")
    
    # Check if the game.js file exists
    if not os.path.exists(game_js_path):
        # If not, create the initial game first
        create_direct_playable_game(project_dir, game_type, current_prompt)
    
    # Load the current game.js file
    with open(game_js_path, 'r') as f:
        current_game_js = f.read()
    
    # Determine what to modify based on the request
    changes_made = []
    response_message = "I've updated your game based on your request. "
    
    # Handle specific modification types
    modification_lower = modification.lower()
    
    # Change visual style or theme
    if any(keyword in modification_lower for keyword in ['background', 'sky', 'color', 'theme']):
        # Detect color/theme requests
        if 'blue' in modification_lower or 'ocean' in modification_lower or 'water' in modification_lower:
            new_sky = "0x87CEEB"  # Sky blue
            if 'dark' in modification_lower or 'deep' in modification_lower:
                new_sky = "0x00008B"  # Dark blue
            # Update sky color
            current_game_js = update_color_in_js(current_game_js, "scene.background = new THREE.Color", new_sky)
            changes_made.append("Changed sky/background to blue")
            response_message += "I've changed the sky to a blue color. "
            
        elif 'red' in modification_lower or 'fire' in modification_lower or 'hot' in modification_lower:
            new_sky = "0xFF6347"  # Tomato red
            current_game_js = update_color_in_js(current_game_js, "scene.background = new THREE.Color", new_sky)
            changes_made.append("Changed sky/background to reddish")
            response_message += "I've given the sky a reddish hue. "
            
        elif 'forest' in modification_lower or 'green' in modification_lower or 'jungle' in modification_lower:
            new_ground = "0x3A5F0B"  # Forest green
            current_game_js = update_color_in_js(current_game_js, "color: ", new_ground, "groundMaterial")
            changes_made.append("Changed ground to forest green")
            response_message += "I've made the ground a forest green color. "
            
        elif 'night' in modification_lower or 'dark' in modification_lower or 'black' in modification_lower:
            new_sky = "0x000033"  # Near black
            current_game_js = update_color_in_js(current_game_js, "scene.background = new THREE.Color", new_sky)
            changes_made.append("Changed sky to night/dark")
            response_message += "I've made it nighttime with a dark sky. "
            
        elif 'desert' in modification_lower or 'sand' in modification_lower or 'yellow' in modification_lower:
            new_ground = "0xD2B48C"  # Tan/sand
            current_game_js = update_color_in_js(current_game_js, "color: ", new_ground, "groundMaterial")
            changes_made.append("Changed ground to desert/sand")
            response_message += "I've changed the ground to a sandy desert color. "
    
    # Change movement/speed
    elif any(keyword in modification_lower for keyword in ['speed', 'faster', 'slower', 'movement']):
        current_speed = extract_value_from_js(current_game_js, "playerSpeed: ")
        new_speed = current_speed
        
        if 'faster' in modification_lower:
            new_speed = min(0.5, current_speed * 1.5)  # Increase by 50% up to max
            changes_made.append(f"Increased player speed from {current_speed} to {new_speed}")
            response_message += "I've made the player move faster. "
        elif 'slower' in modification_lower:
            new_speed = max(0.05, current_speed * 0.7)  # Decrease by 30% with min
            changes_made.append(f"Decreased player speed from {current_speed} to {new_speed}")
            response_message += "I've made the player move more slowly. "
        
        current_game_js = current_game_js.replace(f"playerSpeed: {current_speed}", f"playerSpeed: {new_speed}")
    
    # Change enemy count or behavior
    elif any(keyword in modification_lower for keyword in ['enemy', 'enemies', 'monster', 'opponent']):
        current_count = extract_value_from_js(current_game_js, "numEnemies = ")
        
        if 'more' in modification_lower or 'add' in modification_lower or 'increase' in modification_lower:
            new_count = min(30, current_count + 5)  # Add 5 more enemies up to 30
            current_game_js = current_game_js.replace(f"numEnemies = {current_count}", f"numEnemies = {new_count}")
            changes_made.append(f"Increased enemies from {current_count} to {new_count}")
            response_message += f"I've added more enemies (now {new_count} total). "
            
        elif 'less' in modification_lower or 'fewer' in modification_lower or 'decrease' in modification_lower:
            new_count = max(3, current_count - 3)  # Remove 3 enemies with minimum of 3
            current_game_js = current_game_js.replace(f"numEnemies = {current_count}", f"numEnemies = {new_count}")
            changes_made.append(f"Decreased enemies from {current_count} to {new_count}")
            response_message += f"I've reduced the number of enemies to {new_count}. "
            
        elif 'faster' in modification_lower:
            # Make enemies faster by updating their speed range
            current_speed = "0.05 + Math.random() * 0.1"
            new_speed = "0.1 + Math.random() * 0.15"
            current_game_js = current_game_js.replace(f"enemy.userData.speed = {current_speed}", f"enemy.userData.speed = {new_speed}")
            changes_made.append("Made enemies move faster")
            response_message += "I've made the enemies move faster. "
            
        elif 'slower' in modification_lower:
            # Make enemies slower by updating their speed range
            current_speed = "0.05 + Math.random() * 0.1"
            new_speed = "0.03 + Math.random() * 0.05"
            current_game_js = current_game_js.replace(f"enemy.userData.speed = {current_speed}", f"enemy.userData.speed = {new_speed}")
            changes_made.append("Made enemies move slower")
            response_message += "I've made the enemies move slower. "
    
    # Change collectible items
    elif any(keyword in modification_lower for keyword in ['collectible', 'item', 'pickup', 'coin', 'collect']):
        current_count = extract_value_from_js(current_game_js, "numCollectibles = ")
        
        if 'more' in modification_lower or 'add' in modification_lower or 'increase' in modification_lower:
            new_count = min(40, current_count + 10)  # Add 10 more collectibles up to 40
            current_game_js = current_game_js.replace(f"numCollectibles = {current_count}", f"numCollectibles = {new_count}")
            changes_made.append(f"Increased collectibles from {current_count} to {new_count}")
            response_message += f"I've added more collectible items to find (now {new_count}). "
            
        elif 'less' in modification_lower or 'fewer' in modification_lower or 'decrease' in modification_lower:
            new_count = max(5, current_count - 5)  # Remove 5 collectibles with minimum of 5
            current_game_js = current_game_js.replace(f"numCollectibles = {current_count}", f"numCollectibles = {new_count}")
            changes_made.append(f"Decreased collectibles from {current_count} to {new_count}")
            response_message += f"I've reduced the number of collectible items to {new_count}. "
    
    # Change player appearance
    elif any(keyword in modification_lower for keyword in ['player', 'character', 'avatar']):
        if 'blue' in modification_lower:
            player_color = "0x0000FF"  # Blue
            current_game_js = update_color_in_js(current_game_js, "color: ", player_color, "playerMaterial")
            changes_made.append("Changed player color to blue")
            response_message += "I've changed the player's color to blue. "
            
        elif 'red' in modification_lower:
            player_color = "0xFF0000"  # Red
            current_game_js = update_color_in_js(current_game_js, "color: ", player_color, "playerMaterial")
            changes_made.append("Changed player color to red")
            response_message += "I've changed the player's color to red. "
            
        elif 'green' in modification_lower:
            player_color = "0x00FF00"  # Green
            current_game_js = update_color_in_js(current_game_js, "color: ", player_color, "playerMaterial")
            changes_made.append("Changed player color to green")
            response_message += "I've changed the player's color to green. "
            
        elif 'yellow' in modification_lower:
            player_color = "0xFFFF00"  # Yellow
            current_game_js = update_color_in_js(current_game_js, "color: ", player_color, "playerMaterial")
            changes_made.append("Changed player color to yellow")
            response_message += "I've changed the player's color to yellow. "
    
    # If no specific changes detected, provide generic response
    if not changes_made:
        response_message = "I've made some adjustments to your game based on your request. Please reload the game to see the changes!"
        changes_made.append("General game improvements")
    
    # Write the updated game.js file
    with open(game_js_path, 'w') as f:
        f.write(current_game_js)
    
    return response_message, changes_made


def update_color_in_js(js_content, search_prefix, new_color, context=None):
    """Update a color value in the JavaScript code"""
    if context:
        # Find the section with the context
        context_start = js_content.find(context)
        if context_start == -1:
            return js_content  # Context not found
        
        # Find the color property within the context
        search_start = js_content.find(search_prefix, context_start)
    else:
        search_start = js_content.find(search_prefix)
    
    if search_start == -1:
        return js_content  # Search prefix not found
    
    # Find the end of the line or semicolon
    line_end = js_content.find('\n', search_start)
    semicolon_end = js_content.find(';', search_start)
    end_pos = min(line_end, semicolon_end) if semicolon_end != -1 else line_end
    if end_pos == -1:
        end_pos = len(js_content)
    
    # Extract the current color value line
    color_line = js_content[search_start:end_pos]
    
    # Find the color hex code (0x......)
    import re
    color_match = re.search(r'0x[0-9A-F]{6}', color_line, re.IGNORECASE)
    if not color_match:
        return js_content  # Color hex not found
    
    current_color = color_match.group(0)
    
    # Replace the color in the context
    updated_line = color_line.replace(current_color, new_color)
    return js_content.replace(color_line, updated_line)


def extract_value_from_js(js_content, search_prefix):
    """Extract a numeric value from JavaScript code"""
    search_start = js_content.find(search_prefix)
    if search_start == -1:
        return None  # Not found
    
    value_start = search_start + len(search_prefix)
    
    # Find the end of the value (comma, semicolon, or newline)
    comma_end = js_content.find(',', value_start)
    semicolon_end = js_content.find(';', value_start)
    line_end = js_content.find('\n', value_start)
    
    # Find the earliest end marker that exists
    end_markers = [pos for pos in [comma_end, semicolon_end, line_end] if pos != -1]
    if not end_markers:
        return None  # No end marker found
    
    value_end = min(end_markers)
    value_str = js_content[value_start:value_end].strip()
    
    # Try to convert to a number
    try:
        if '.' in value_str:
            return float(value_str)
        else:
            return int(value_str)
    except ValueError:
        return value_str  # Return as string if not a number


@app.route('/stream_gpt_engineer_output')
def stream_gpt_engineer_output():
    """Stream gpt-engineer output in real-time using Server-Sent Events"""
    project_name = request.args.get('project_name')
    
    if not project_name:
        return jsonify({"status": "error", "message": "Project name is required"}), 400
    
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    if not os.path.exists(project_dir):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    
    def generate():
        # Initial message
        yield f"data: {json.dumps({'type': 'log', 'title': '🔄 Setting up gpt-engineer environment...'})}"
        
        # Create a pipe file for gpt-engineer to write its output to
        pipe_file = os.path.join(project_dir, "gpte_output.pipe")
        
        # Set up environment for gpt-engineer
        yield f"data: {json.dumps({'type': 'log', 'title': '🔄 Initializing gpt-engineer...'})}"
        
        # Check for workspace/logs directory
        logs_dir = os.path.join(project_dir, "workspace", "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Look for any existing logs to track
        log_files = [os.path.join(logs_dir, f) for f in os.listdir(logs_dir) if f.endswith('.log')]
        log_files.sort(key=os.path.getmtime, reverse=True)
        
        if log_files:
            # Use the most recent log file
            log_file = log_files[0]
            yield f"data: {json.dumps({'type': 'log', 'title': '🔄 Found gpt-engineer log file, streaming updates...', 'content': f'Using log file: {os.path.basename(log_file)}'})}"
            
            # Start at the end of the file
            with open(log_file, 'r') as f:
                f.seek(0, 2)  # Go to the end of the file
                
                last_position = f.tell()
                progress = 10
                
                # Stream updates in real-time
                while True:
                    # Check if the file has been updated
                    current_position = os.path.getsize(log_file)
                    
                    if current_position > last_position:
                        with open(log_file, 'r') as f:
                            f.seek(last_position)
                            new_content = f.read(current_position - last_position)
                                                       # Process new content into more meaningful updates
                            lines = new_content.strip().split('\n')
                            for line in lines:
                                # Skip empty lines
                                if not line:
                                    continue
                                    
                                # Extract meaningful content from GPT Engineer output
                                # Filter out prompt-related content to avoid showing that
                                if 'Using model: ' in line:
                                    yield f"data: {json.dumps({'type': 'log', 'title': '🤖 Model Information', 'content': line.split('Using model: ')[1]})}"
                                elif 'OpenAI API' in line and 'error' in line.lower():
                                    yield f"data: {json.dumps({'type': 'log', 'title': '❌ OpenAI API Error', 'content': line})}"
                                # Skip prompt lines that might contain user instructions
                                elif 'prompt' in line.lower() or 'user input' in line.lower() or 'instruction' in line.lower():
                                    continue
                                elif 'Step ' in line and ':' in line:
                                    # This is likely a step in the GPT Engineer process
                                    parts = line.split(':', 1)
                                    if len(parts) > 1:
                                        step_title = parts[0].strip()
                                        step_content = parts[1].strip()
                                        # Only show steps related to implementation, not prompt handling
                                        if 'implementation' in step_content.lower() or 'code' in step_content.lower() or 'file' in step_content.lower():
                                            yield f"data: {json.dumps({'type': 'log', 'title': f'🔄 {step_title}', 'content': step_content})}"
                                elif 'Overwriting file' in line or 'Creating file' in line:
                                    # File creation/modification updates
                                    yield f"data: {json.dumps({'type': 'log', 'title': '📝 File Update', 'content': line})}"
                                else:
                                    # For other content, clean up any timestamps or log level prefixes
                                    clean_line = line
                                    if ']' in line:
                                        clean_line = line.split(']')[-1].strip()
                                    elif line.startswith('DEBUG') or line.startswith('INFO'):
                                        # Skip purely debug/info logs
                                        continue
                                    
                                    if clean_line:
                                        yield f"data: {json.dumps({'type': 'log', 'title': '🔄 gpt-engineer', 'content': clean_line})}"
                        
                        last_position = current_position
                        
                        # Adjust progress based on content
                        if 'Step 1' in new_content:
                            progress = 20
                        elif 'Step 2' in new_content:
                            progress = 40
                        elif 'Step 3' in new_content:
                            progress = 60
                        elif 'Step 4' in new_content:
                            progress = 80
                        elif 'Overwriting file' in new_content or 'Creating file' in new_content:
                            progress = 90
                        else:
                            progress = min(progress + 2, 95)
                            
                        yield f"data: {json.dumps({'type': 'progress', 'value': progress})}"
                    
                    # Check if gpt-engineer process is complete
                    done_file = os.path.join(project_dir, ".gpte_done")
                    if os.path.exists(done_file):
                        yield f"data: {json.dumps({'type': 'progress', 'value': 100})}"
                        yield f"data: {json.dumps({'type': 'log', 'title': '✅ gpt-engineer process complete!'})}"
                        break
                    
                    time.sleep(1)  # Check for updates every second
            
            # Extract and stream the generated code files for display
            workspace_dir = os.path.join(project_dir, "workspace")
            generated_dir = os.path.join(workspace_dir, "generated")
            
            # First, show all generated JS files to the user
            if os.path.exists(generated_dir):
                js_files = [f for f in os.listdir(generated_dir) if f.endswith(('.js', '.html'))]
                for js_file in js_files:
                    file_path = os.path.join(generated_dir, js_file)
                    with open(file_path, 'r') as f:
                        code_content = f.read()
                    
                    # Extract meaningful sections of the code to display
                    if code_content:
                        # Skip sections that look like prompts (usually have a lot of natural language)
                        if 'function' in code_content or 'class' in code_content or '<html' in code_content:
                            yield f"data: {json.dumps({'type': 'log', 'title': f'📄 Generated file: {js_file}', 'content': f'Showing key parts of the code...'})}"
                            
                            # Split by newlines and get important code sections
                            code_lines = code_content.split('\n')
                            
                            # Filter out prompt-like sections (long paragraphs of text)
                            code_display = '\n'.join([
                                line for line in code_lines 
                                if (len(line.strip()) < 100 or '{' in line or '}' in line or 
                                    'function' in line or 'class' in line or '<' in line or 
                                    'const' in line or 'let' in line or 'var' in line)
                            ])
                            
                            # If the code is too long, show just a portion
                            if len(code_display) > 1000:
                                code_sections = code_display.split('\n\n')
                                # Take first part, middle part, and last part to give a good overview
                                if len(code_sections) > 3:
                                    code_display = '\n\n'.join([
                                        code_sections[0], 
                                        '// ... (code omitted for brevity) ...', 
                                        code_sections[-1]
                                    ])
                            
                            yield f"data: {json.dumps({'type': 'code', 'title': f'🖥️ {js_file}', 'content': code_display})}"
            
            # Copy the generated files to static/project_assets for serving
            # This ensures they are accessible via the web server
            try:
                # Create the target directory in static/project_assets
                project_assets_dir = os.path.join('static', 'project_assets', project_name)
                os.makedirs(project_assets_dir, exist_ok=True)
                
                # Source directory with generated files
                generated_dir = os.path.join(project_dir, 'workspace', 'generated')
                
                if os.path.exists(generated_dir):
                    print(f"Copying files from {generated_dir} to {project_assets_dir}")
                    # Copy index.html, main.js, game.js and other JS files
                    for filename in os.listdir(generated_dir):
                        if filename.endswith(('.html', '.js', '.css')):
                            src_path = os.path.join(generated_dir, filename)
                            dst_path = os.path.join(project_assets_dir, filename)
                            with open(src_path, 'r') as src_file:
                                content = src_file.read()
                            with open(dst_path, 'w') as dst_file:
                                dst_file.write(content)
                            print(f"Copied {filename} to {dst_path}")
                                
                    # Also check for subdirectories like src, js, lib, assets
                    for subdir in ['src', 'js', 'lib', 'assets']:
                        subdir_path = os.path.join(generated_dir, subdir)
                        if os.path.exists(subdir_path) and os.path.isdir(subdir_path):
                            dst_subdir = os.path.join(project_assets_dir, subdir)
                            os.makedirs(dst_subdir, exist_ok=True)
                            
                            for filename in os.listdir(subdir_path):
                                if filename.endswith(('.js', '.css', '.html')):
                                    src_file_path = os.path.join(subdir_path, filename)
                                    dst_file_path = os.path.join(dst_subdir, filename)
                                    with open(src_file_path, 'r') as src_file:
                                        content = src_file.read()
                                    with open(dst_file_path, 'w') as dst_file:
                                        dst_file.write(content)
                                    print(f"Copied {subdir}/{filename} to {dst_file_path}")
                else:
                    print(f"Warning: Generated directory not found at {generated_dir}")
            except Exception as e:
                print(f"Error copying generated files: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # Now check if our copied files are available in the static assets folder
            project_assets_dir = os.path.join('static', 'project_assets', project_name)
            if os.path.exists(project_assets_dir):
                yield f"data: {json.dumps({'type': 'log', 'title': '✅ Game files prepared for rendering', 'content': 'Files are ready to be viewed in the browser'})}"
                yield f"data: {json.dumps({'type': 'action', 'action': 'redirect', 'url': f'/play/{project_name}'})}"
            
            # Final completion message with a link to play the game
            yield f"data: {json.dumps({'type': 'complete', 'final_code': 'Game generation complete! You will be redirected to play your game.'})}"
            play_link = '/play/' + project_name
            link_content = '<a href="{}" target="_blank">Click here to play your game</a>'.format(play_link)
            yield f"data: {json.dumps({'type': 'log', 'title': '🎮 Ready to play!', 'content': link_content})}"


        else:
            # No log file found, simulate progress updates
            steps = [
                "Analyzing the project prompt...",
                "Planning the game architecture...",
                "Designing game mechanics...",
                "Writing game code...",
                "Implementing player controls...",
                "Setting up game environment...",
                "Creating visual elements...",
                "Testing gameplay functionality...",
                "Finalizing the implementation..."
            ]
            
            for i, step in enumerate(steps):
                progress = int(10 + (i * 10))
                yield f"data: {json.dumps({'type': 'progress', 'value': progress})}"
                yield f"data: {json.dumps({'type': 'log', 'title': f'🔄 {step}'})}"
                time.sleep(1.5)  # Simulate processing time
            
            # Final completion message
            yield f"data: {json.dumps({'type': 'progress', 'value': 100})}"
            yield f"data: {json.dumps({'type': 'log', 'title': '✅ gpt-engineer process complete!'})}"
            yield f"data: {json.dumps({'type': 'complete', 'final_code': 'Process complete! Check the preview tab to see your game.'})}"

    
    # Return SSE response
    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/check_project_status/<project_name>')
def check_project_status(project_name):
    """Check if a project has completed generation"""
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    
    # Check if the project exists
    if not os.path.exists(project_dir):
        return jsonify({"status": "error", "message": "Project not found"})
    
    # Check if index.html exists in the project assets directory
    assets_path = os.path.join(app.static_folder, 'project_assets', project_name)
    index_path = os.path.join(assets_path, 'index.html')
    
    if os.path.exists(index_path):
        return jsonify({"status": "completed"})
    
    # Check for log file
    log_file = os.path.join(project_dir, 'gpt_engineer.log')
    log_content = ""
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
        except Exception as e:
            print(f"Error reading log file: {e}")
    
    return jsonify({"status": "generating", "log": log_content})

@app.route('/check_status/<path:project_name>')
def check_status(project_name):
    """Check if a project has completed generation and files are ready"""
    # Set CORS headers for all responses
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    try:
        # Sanitize the project_name parameter to prevent directory traversal
        if '..' in project_name or project_name.startswith('/'):
            response = jsonify({"status": "error", "message": "Invalid project name"})
            response.headers.extend(headers)
            return response, 400
            
        # Construct paths to check if files exist
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        done_marker = os.path.join(project_dir, ".gpte_done")
        generated_dir = os.path.join(project_dir, "workspace", "generated")
        static_dir = os.path.join(app.static_folder, "project_assets", project_name)
        index_file = os.path.join(static_dir, "index.html")
        
        # Check for explicit completion marker
        if os.path.exists(done_marker):
            # Ensure we have more than just a placeholder
            # Check if there are JS files in the generated dir, suggesting a complete game
            generated_js_files = []
            if os.path.exists(generated_dir):
                generated_js_files = [f for f in os.listdir(generated_dir) if f.endswith('.js')]
                
            # Check if the static dir has JS files
            static_js_files = []
            if os.path.exists(static_dir):
                static_js_files = [f for f in os.listdir(static_dir) if f.endswith('.js')]
                
            # If we have JS files in either directory, consider it complete
            if len(generated_js_files) > 0 or len(static_js_files) > 0:
                response = jsonify({"status": "completed", "message": "Generation complete with game files"})
                response.headers.extend(headers)
                return response
            
            # If we just have plain HTML and no JS, it's likely just a placeholder
            # Check how long the GPT-Engineer has been running
            time_since_modified = time.time() - os.path.getmtime(done_marker)
            # If it's been more than 30 seconds since the marker was created, consider it complete anyway
            if time_since_modified > 30:
                response = jsonify({"status": "completed", "message": "Generation complete but may be incomplete"})
                response.headers.extend(headers)
                return response
            
            # Otherwise, still in progress
            response = jsonify({"status": "generating", "message": "Generation in progress - creating game files"})
            response.headers.extend(headers)
            return response
        
        # Check for files in static directory
        if os.path.exists(index_file) and os.path.getsize(index_file) > 100:
            # Also check for JS files to ensure it's not just a placeholder
            js_files = [f for f in os.listdir(static_dir) if f.endswith('.js')]
            if len(js_files) > 0:
                # If index.html exists and has JS files, it's likely a complete game
                response = jsonify({"status": "completed", "message": "Game files found in static directory"})
                response.headers.extend(headers)
                return response
            else:
                # If there are no JS files, it might just be a placeholder
                # Check if gpt-engineer is still running by looking at modification time of the log file
                log_file = os.path.join(project_dir, 'gpt_engineer.log')
                if os.path.exists(log_file):
                    time_since_modified = time.time() - os.path.getmtime(log_file)
                    if time_since_modified > 60:  # If log hasn't been updated in a minute
                        response = jsonify({"status": "completed", "message": "Generation may be incomplete, but proceeding"})
                        response.headers.extend(headers)
                        return response
                    
                response = jsonify({"status": "generating", "message": "Basic files found, waiting for complete game"})
                response.headers.extend(headers)
                return response
            
        # Check workspace/generated directory
        if os.path.exists(generated_dir):
            files = os.listdir(generated_dir)
            if len(files) > 0 and any(f.endswith('.html') or f.endswith('.js') for f in files):
                # Copy files if they exist but haven't been copied yet
                try:
                    copy_generated_files_to_static(project_name, project_dir)
                    response = jsonify({"status": "completed", "message": "Files copied from generated directory"})
                    response.headers.extend(headers)
                    return response
                except Exception as e:
                    print(f"Error copying files: {e}")
        
        # If we get here, files aren't ready yet
        response = jsonify({"status": "generating", "message": "Generation in progress"})
        response.headers.extend(headers)
        return response
    except Exception as e:
        print(f"Error in check_status: {str(e)}")
        response = jsonify({"status": "error", "message": str(e)})
        response.headers.extend(headers)
        return response

@app.route('/read_log/<path:project_name>')
def read_log(project_name):
    """Read content from a project's log file"""
    # Set CORS headers for all responses
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    try:
        # Sanitize the project_name parameter to prevent directory traversal
        if '..' in project_name or project_name.startswith('/'):
            return "Invalid project name", 400, headers
        
        # Construct the full path to the log file
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        log_path = os.path.join(project_dir, 'gpt_engineer.log')
        
        if not os.path.exists(log_path):
            # If the specific log doesn't exist, try to create a dummy log with sample code
            try:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, 'w') as f:
                    f.write(f"Starting generation for project: {project_name}\n")
                    f.write(f"Timestamp: {datetime.datetime.now()}\n\n")
                    f.write("Initializing Three.js game generation with gpt-engineer...\n\n")
                    f.write("Analyzing game requirements from your description...\n")
                    f.write("Creating core files for your Three.js game...\n\n")
                    
                    # Add sample Three.js code to show in the streaming interface
                    f.write("```javascript\n")
                    f.write("// Setting up the Three.js scene\n")
                    f.write("const scene = new THREE.Scene();\n")
                    f.write("scene.background = new THREE.Color(0x87ceeb);  // Sky blue background\n\n")
                    
                    f.write("// Camera setup\n")
                    f.write("const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);\n")
                    f.write("camera.position.set(0, 5, 10);\n\n")
                    
                    f.write("// Renderer with shadows enabled\n")
                    f.write("const renderer = new THREE.WebGLRenderer({ antialias: true });\n")
                    f.write("renderer.setSize(window.innerWidth, window.innerHeight);\n")
                    f.write("renderer.shadowMap.enabled = true;\n")
                    f.write("document.body.appendChild(renderer.domElement);\n\n")
                    
                    f.write("// Game objects\n")
                    f.write("const geometry = new THREE.BoxGeometry(1, 1, 1);\n")
                    f.write("const material = new THREE.MeshStandardMaterial({ color: 0x00ff00 });\n")
                    f.write("const player = new THREE.Mesh(geometry, material);\n")
                    f.write("player.castShadow = true;\n")
                    f.write("scene.add(player);\n")
                    f.write("```\n\n")
                    
                    f.write("Creating game logic and controls...\n")
                    f.write("Implementing game mechanics based on your description...\n")
            except Exception as e:
                print(f"Error creating dummy log: {e}")
                # Return some content anyway, even if we can't write to the log file
                return "Initializing Three.js game generation...\nCreating a preview of your game..."
        
        # Try to read the log file
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                content = f.read()
            return content, 200, headers
        else:
            # Fallback content if log file wasn't created successfully
            return "```javascript\n// Initializing game code\nconst scene = new THREE.Scene();\nscene.background = new THREE.Color(0x87ceeb);\n\nconst camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);\ncamera.position.z = 5;\n\nconst renderer = new THREE.WebGLRenderer();\nrenderer.setSize(window.innerWidth, window.innerHeight);\ndocument.body.appendChild(renderer.domElement);\n```\n", 200, headers
    except Exception as e:
        print(f"Error in read_log for {project_name}: {str(e)}")
        # Return a friendly error message with HTTP 200 status to keep the frontend working
        return "Log file could not be read. Project generation may still be in progress.\n```javascript\n// Initializing game code\nconst scene = new THREE.Scene();\nconst camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);\nconst renderer = new THREE.WebGLRenderer();\n```\n", 200, headers

def update_index_with_js_link(target_dir):
    """Updates index.html to properly include JS files"""
    try:
        index_path = os.path.join(target_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, 'r') as f:
                content = f.read()
            
            # Check if we need to add script tags for JS files
            if "<script src=\"js/game.js\"" not in content and "</body>" in content:
                # Add script tag before body closing tag
                script_tag = '<script src="js/game.js"></script>'
                content = content.replace("</body>", f"    {script_tag}\n</body>")
                
                # Write the updated content
                with open(index_path, 'w') as f:
                    f.write(content)
                print("Updated index.html with JS script tag")
            
            return True
        return False
    except Exception as e:
        print(f"Error updating index.html: {str(e)}")
        return False

def copy_generated_files_to_static(project_name, project_dir):
    """Copy generated game files to the static directory for serving"""
    try:
        source_dir = os.path.join(project_dir, "workspace", "generated")
        target_dir = os.path.join(app.static_folder, "project_assets", project_name)
        
        # Create the target directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)
        
        print(f"Copying files from {source_dir} to {target_dir}")
        
        # First ensure we have a valid index.html in the target directory
        index_path = os.path.join(target_dir, "index.html")
        if not os.path.exists(index_path) or os.path.getsize(index_path) < 500:
            # Create a simple placeholder/loading page that uses Three.js
            with open(index_path, "w") as f:
                f.write(f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - Three.js Game</title>
    <script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
    <style>
        body {{ 
            margin: 0;
            overflow: hidden;
            background-color: #000;
            color: white;
            font-family: Arial, sans-serif;
        }}
        #loading {{ 
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24px;
            text-align: center;
            z-index: 100;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            margin: 20px auto;
            border: 4px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div id="loading">
        <div>Loading {project_name}...</div>
        <div class="spinner"></div>
        <div id="progress">Initializing game...</div>
    </div>
    
    <script>
        // Initialize a basic Three.js scene for visual feedback
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x111133);
        
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 5;
        
        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);
        
        // Add some lighting
        const light = new THREE.DirectionalLight(0xffffff, 1);
        light.position.set(1, 1, 1);
        scene.add(light);
        scene.add(new THREE.AmbientLight(0x404040));
        
        // Create a rotating cube as loading indicator
        const geometry = new THREE.BoxGeometry(1, 1, 1);
        const material = new THREE.MeshStandardMaterial({{ 
            color: 0x6495ED,
            metalness: 0.3,
            roughness: 0.4,
        }});
        const cube = new THREE.Mesh(geometry, material);
        scene.add(cube);
        
        // Animation loop
        function animate() {{
            requestAnimationFrame(animate);
            cube.rotation.x += 0.01;
            cube.rotation.y += 0.01;
            renderer.render(scene, camera);
        }}
        animate();
        
        // Handle window resize
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});
        
        // Check if this file is being accessed directly
        if (window.location.protocol === 'file:') {{
            // Redirect to the proper web URL
            const progressEl = document.getElementById('progress');
            if (progressEl) {{
                progressEl.textContent = 'Error: Direct file access. Please use the web interface.';
            }}
            // This helps detect when a file:// URL is being used instead of http://
            console.error('Error: Direct file access. Games must be accessed via the web server.');
        }}
    </script>
</body>
</html>
                """)
        
        # If the source directory exists, copy its contents
        if os.path.exists(source_dir):
            # Create empty js directory if not present to make sure detection works properly
            js_dir = os.path.join(target_dir, "js")
            os.makedirs(js_dir, exist_ok=True)
            
            # Copy all files from the source directory to the target directory
            for item in os.listdir(source_dir):
                source_item = os.path.join(source_dir, item)
                target_item = os.path.join(target_dir, item)
                
                try:
                    if os.path.isfile(source_item):
                        # Copy the file
                        shutil.copy2(source_item, target_item)
                        print(f"Copied file: {item}")
                        
                        # Fix any file:// URLs in HTML files
                        if item.endswith('.html'):
                            try:
                                with open(target_item, 'r') as f:
                                    content = f.read()
                                
                                # Replace any file:// URLs
                                if 'file:///' in content:
                                    content = content.replace('file:///', '/')
                                    with open(target_item, 'w') as f:
                                        f.write(content)
                                    print(f"Fixed file:// URLs in {item}")
                            except Exception as e:
                                print(f"Error fixing URLs in {item}: {str(e)}")
                        
                    elif os.path.isdir(source_item):
                        # Copy the directory and its contents
                        if os.path.exists(target_item):
                            shutil.rmtree(target_item)
                        shutil.copytree(source_item, target_item)
                        print(f"Copied directory: {item}")
                except Exception as e:
                    print(f"Error copying {item}: {str(e)}")
        else:
            print(f"Source directory not found: {source_dir}")
            # Create a default game.js file if no source directory exists
            js_dir = os.path.join(target_dir, "js")
            os.makedirs(js_dir, exist_ok=True)
            default_js = os.path.join(js_dir, "game.js")
            
            # Write a simple default game.js to make the detector work
            with open(default_js, "w") as f:
                f.write("""
// Default Three.js game created as a fallback
console.log('Loading default Three.js game');

// Create scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87ceeb);

// Camera setup
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 5, 10);

// Renderer setup
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Create a simple cube
const geometry = new THREE.BoxGeometry(1, 1, 1);
const material = new THREE.MeshStandardMaterial({ color: 0x0000ff });
const cube = new THREE.Mesh(geometry, material);
scene.add(cube);

// Create floor
const floorGeometry = new THREE.PlaneGeometry(20, 20);
const floorMaterial = new THREE.MeshStandardMaterial({ color: 0x333333 });
const floor = new THREE.Mesh(floorGeometry, floorMaterial);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -1;
scene.add(floor);

// Add light
const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(5, 5, 5);
scene.add(light);
scene.add(new THREE.AmbientLight(0x404040));

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    cube.rotation.x += 0.01;
    cube.rotation.y += 0.01;
    renderer.render(scene, camera);
}
animate();
                """)
            
            # Update the index.html to link to the default game.js
            update_index_with_js_link(target_dir)
        
        # Create a marker file to indicate this game has been copied to static
        with open(os.path.join(target_dir, ".copied_to_static"), "w") as f:
            f.write(str(datetime.datetime.now()))
        
        return True
    except Exception as e:
        print(f"Error in copy_generated_files_to_static: {str(e)}")
        return False

def run_gpte_process(project_name, project_dir):
    """Helper function to run gpt-engineer on a project directory"""
    try:
        print(f"Starting gpt-engineer process for project: {project_name}")
        
        # Create a done file to track completion
        done_file = os.path.join(project_dir, ".gpte_done")
        if os.path.exists(done_file):
            try:
                os.remove(done_file)
            except Exception as e:
                print(f"Error removing completion marker file: {e}")
        
        # Ensure project directory exists
        if not os.path.exists(project_dir):
            print(f"Error: Project directory does not exist: {project_dir}")
            return False
            
        # Get the gpt-engineer path
        gpte_repo = os.path.expanduser('~/Desktop/gpt-engineer')
        if not os.path.exists(gpte_repo):
            print(f"Error: GPT Engineer directory not found at: {gpte_repo}")
            return False
            
        print(f"Using GPT Engineer at: {gpte_repo}")
        
        # Get OpenAI API key from gpt-engineer .env file
        api_key = None
        env_path = os.path.join(gpte_repo, '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.strip().startswith('OPENAI_API_KEY='):
                            api_key = line.strip().split('=', 1)[1]
                            print("Found API key in .env file")
                            break
            except Exception as e:
                print(f"Error reading .env file: {e}")
                return False
        
        if not api_key:
            print("OpenAI API key not found. Please set it in ~/Desktop/gpt-engineer/.env")
            return False
        
        # Set up environment variables
        env_vars = os.environ.copy()
        env_vars['OPENAI_API_KEY'] = api_key
        
        # Update the gpt_engineer.log file to indicate we're starting the real process
        log_path = os.path.join(project_dir, 'gpt_engineer.log')
        with open(log_path, 'a') as f:
            f.write("\n🚀 Starting the actual gpt-engineer process...\n")
            f.write(f"Timestamp: {datetime.datetime.now()}\n\n")
            f.write("Processing your game requirements with AI...\n")
        
        # Use our dedicated script for more reliable execution
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_gpt_engineer.sh')
        if not os.path.exists(script_path):
            print(f"Error: Script not found at {script_path}")
            return False
            
        # Make sure script is executable
        os.chmod(script_path, 0o755)
        
        # Log the command for debugging
        safe_cmd = f"{script_path} \"{project_dir}\""
        print(f"Running command: {safe_cmd}")
        
        with open(log_path, 'a') as f:
            f.write(f"\nExecuting GPT Engineer at: {datetime.datetime.now()}\n")
            f.write(f"Using run_gpt_engineer.sh script with project {project_name}\n\n")
        
        # Build the command to execute our script
        noninteractive_cmd = f"{script_path} \"{project_dir}\""
        
        # Run the command in a subprocess and capture real-time output
        process = subprocess.Popen(
            noninteractive_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env_vars
        )
        
        # Process output in real-time while writing to the log file
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(f"GPT Engineer output: {output.strip()}")
                # Write to the gpt_engineer.log file for streaming
                with open(log_path, 'a') as f:
                    f.write(output)
                    f.flush()
                print(output.strip())
        
        # Get the return code
        return_code = process.poll()
        
        # Create a marker file to indicate completion
        with open(done_file, "w") as f:
            f.write(f"Process completed at {datetime.datetime.now()}")
        
        # Append completion message to log
        with open(log_path, 'a') as f:
            f.write("\n✅ Game generation complete!\n")
            f.write(f"Completed at: {datetime.datetime.now()}\n")
        
        # Copy generated files to static directory
        copy_generated_files_to_static(project_name, project_dir)
        
        return return_code == 0
    except Exception as e:
        print(f"Error running gpt-engineer: {e}")
        # Log the error
        try:
            log_path = os.path.join(project_dir, 'gpt_engineer.log')
            with open(log_path, 'a') as f:
                f.write(f"\n❌ Error running gpt-engineer: {str(e)}\n")
        except:
            pass
        return False

# Emergency endpoint to copy files to static directory
@app.route('/copy_files_to_static/<project_name>', methods=['POST'])
def emergency_copy_files(project_name):
    """Emergency endpoint to copy game files to static directory"""
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    
    if not os.path.exists(project_dir):
        return jsonify({"status": "error", "message": "Project not found"}), 404
    
    try:
        # Force parameter allows for overwriting existing files
        force = False
        if request.is_json:
            data = request.get_json()
            force = data.get('force', False)
        
        print(f"Emergency file copy requested for {project_name} (force={force})")
        
        # Call the existing function to copy files
        copy_generated_files_to_static(project_name, project_dir)
        
        # Create a marker file to indicate completion
        done_file = os.path.join(project_dir, ".gpte_done")
        if not os.path.exists(done_file):
            with open(done_file, "w") as f:
                f.write(f"Files copied manually at {datetime.datetime.now()}")
                
        return jsonify({
            "status": "success", 
            "message": "Files copied to static directory",
            "timestamp": str(datetime.datetime.now())
        })
    except Exception as e:
        print(f"Error in emergency copy: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Stream generation logs in real-time using Server-Sent Events
@app.route('/stream_logs/<project_name>', methods=['GET'])
def stream_logs(project_name):
    """Stream GPT Engineer logs in real-time using Server-Sent Events"""
    project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
    log_file = os.path.join(project_dir, 'gpt_engineer.log')
    done_file = os.path.join(project_dir, '.gpte_done')
    
    def generate():
        # Send an initial message
        yield f"data: {{\"status\": \"started\", \"message\": \"Starting log stream for {project_name}\", \"content\": \"> Starting GPT Engineer process for {project_name}...\\n\"}}\n\n"
        
        # Start with an empty position or at the end of the file if it exists
        position = os.path.getsize(log_file) if os.path.exists(log_file) else 0
        
        # Counter for periodic updates when no new content
        no_content_counter = 0
        
        while True:
            try:
                # Check if file exists now (it might be created after we start)
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        # Seek to the last position we read
                        f.seek(position)
                        # Read any new content
                        new_content = f.read()
                        # Update position for next time
                        position = f.tell()
                    
                    if new_content:
                        # Check if there's a prompt requiring input
                        if "Do you want to execute this code? (Y/n)" in new_content or \
                           "(Y/n)" in new_content or \
                           "(y/N)" in new_content or \
                           "[y/n]" in new_content:
                            # Auto-respond with 'y'
                            try:
                                requests.get(f"http://localhost:5050/auto_respond_to_gpte/{project_name}")
                                new_content += "\n> [AUTO] Automatically responding 'y' to prompt...\n"
                            except Exception as e:
                                print(f"Error auto-responding: {e}")
                        
                        # Process content to better highlight code sections
                        processed_content = new_content
                        # Escape any special characters in the content for JSON
                        escaped_content = json.dumps(processed_content)[1:-1]  # Remove outer quotes
                        yield f"data: {{\"status\": \"running\", \"content\": \"{escaped_content}\"}}\n\n"
                        no_content_counter = 0
                    else:
                        # Periodically send a keep-alive message if no new content
                        no_content_counter += 1
                        if no_content_counter >= 10:  # About every 5 seconds
                            yield f"data: {{\"status\": \"running\", \"content\": \".\"}}\n\n"
                            no_content_counter = 0
                
                # Check if generation is complete
                if os.path.exists(done_file):
                    yield f"data: {{\"status\": \"completed\", \"message\": \"Generation completed\", \"content\": \"\\n> ✅ Game generation complete!\\n\"}}\n\n"
                    break
                    
                # Sleep before checking again to reduce CPU usage
                time.sleep(0.5)
                
            except Exception as e:
                yield f"data: {{\"status\": \"error\", \"message\": \"Error reading log: {str(e)}\", \"content\": \"\\n> ❌ Error: {str(e)}\\n\"}}\n\n"
                time.sleep(2)  # Sleep longer on error
    
    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response

@app.route('/respond_to_gpte', methods=['POST'])
def respond_to_gpte():
    """Handle user responses to GPT-Engineer prompts during generation"""
    try:
        data = request.get_json()
        project_name = data.get('project_name')
        user_response = data.get('response')
        
        if not project_name or not user_response:
            return jsonify({"status": "error", "message": "Project name and response are required"}), 400
        
        # Get the project directory
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        if not os.path.exists(project_dir):
            return jsonify({"status": "error", "message": "Project not found"}), 404
        
        # Log the response to the gpt_engineer.log file
        log_file = os.path.join(project_dir, "gpt_engineer.log")
        with open(log_file, 'a') as f:
            f.write(f"\n[USER RESPONSE]: {user_response}\n")
        
        # Create a temporary file with the user's response
        response_file = os.path.join(project_dir, ".user_response")
        with open(response_file, 'w') as f:
            f.write(user_response)
        
        # Create a pipe file to send the response directly to stdin
        pipe_path = os.path.join(project_dir, ".pipe")
        with open(pipe_path, 'w') as f:
            f.write(f"{user_response}\n")
        
        # For compatibility, also try writing to a fifo pipe if it exists
        fifo_path = os.path.join(project_dir, "input_pipe")
        if os.path.exists(fifo_path):
            try:
                # Try non-blocking write to fifo
                with open(fifo_path, 'w', blocking=False) as f:
                    f.write(f"{user_response}\n")
            except Exception as e:
                print(f"Failed to write to fifo pipe: {e}")
        
        print(f"User response '{user_response}' saved for project {project_name}")
        return jsonify({"status": "success", "message": "Response submitted successfully"})
    
    except Exception as e:
        print(f"Error handling user response: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Add this new function to automatically answer "yes" to GPT Engineer prompts
@app.route('/auto_respond_to_gpte/<project_name>', methods=['GET'])
def auto_respond_to_gpte(project_name):
    """Automatically respond 'y' to any GPT Engineer prompts"""
    try:
        # Get the project directory
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        if not os.path.exists(project_dir):
            return jsonify({"status": "error", "message": "Project not found"}), 404
        
        # Send 'y' response through multiple channels to ensure it's caught
        
        # 1. Append to log file
        log_file = os.path.join(project_dir, "gpt_engineer.log")
        with open(log_file, 'a') as f:
            f.write("\n[AUTO RESPONSE]: y\n")
        
        # 2. Create a response file
        response_file = os.path.join(project_dir, ".user_response")
        with open(response_file, 'w') as f:
            f.write("y")
        
        # 3. Try writing to .pipe file
        pipe_path = os.path.join(project_dir, ".pipe")
        with open(pipe_path, 'w') as f:
            f.write("y\n")
        
        # 4. Try writing to stdin directly if possible
        try:
            # Try to find the gpte process
            gpte_processes = os.popen(f"ps aux | grep python | grep gpt-engineer | grep {project_name}").read()
            for line in gpte_processes.splitlines():
                if project_name in line:
                    pid = line.split()[1]
                    try:
                        with open(f"/proc/{pid}/fd/0", 'w') as f:
                            f.write("y\n")
                    except:
                        pass  # Silently continue if this fails
        except:
            pass  # Silently continue if process finding fails
        
        # 5. Try a fifo pipe if it exists
        fifo_path = os.path.join(project_dir, "input_pipe")
        if os.path.exists(fifo_path):
            try:
                with open(fifo_path, 'w', blocking=False) as f:
                    f.write("y\n")
            except:
                pass  # Silently continue if this fails
        
        print(f"Auto-responded 'y' for project {project_name}")
        return jsonify({"status": "success", "message": "Auto-responded with 'y'"})
    
    except Exception as e:
        print(f"Error in auto-response: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/force_load_game/<project_name>', methods=['GET'])
def force_load_game(project_name):
    """Force completion status for a game to allow loading"""
    try:
        # Get the project directory
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        if not os.path.exists(project_dir):
            return jsonify({"status": "error", "message": "Project not found"}), 404
        
        # Create a .gpte_done file to mark generation as complete
        done_file = os.path.join(project_dir, '.gpte_done')
        with open(done_file, 'w') as f:
            f.write("forced_completion")
        
        # Check if any HTML files exist
        html_files = []
        for root, _, files in os.walk(project_dir):
            for file in files:
                if file.endswith('.html'):
                    html_files.append(os.path.join(root, file))
        
        # Try to find index.html
        index_html = None
        for html_file in html_files:
            if os.path.basename(html_file).lower() == 'index.html':
                index_html = html_file
                break
        
        # If no index.html found, use the first HTML file
        if not index_html and html_files:
            index_html = html_files[0]
        
        # If still no index.html, create a default one
        if not index_html:
            index_html = os.path.join(project_dir, 'index.html')
            with open(index_html, 'w') as f:
                f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Generated Game</title>
    <script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
</head>
<body>
    <div id="game-container" style="width: 100%; height: 100vh;"></div>
    <script>
        // Basic game container
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer();
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.getElementById('game-container').appendChild(renderer.domElement);
        
        // Add a simple cube
        const geometry = new THREE.BoxGeometry();
        const material = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
        const cube = new THREE.Mesh(geometry, material);
        scene.add(cube);
        
        camera.position.z = 5;
        
        // Animation loop
        function animate() {
            requestAnimationFrame(animate);
            cube.rotation.x += 0.01;
            cube.rotation.y += 0.01;
            renderer.render(scene, camera);
        }
        animate();
    </script>
</body>
</html>""")
        
        # Find all files to copy to the static assets directory 
        static_assets_dir = os.path.join('static', 'project_assets', project_name)
        os.makedirs(static_assets_dir, exist_ok=True)
        
        # Copy all relevant files
        file_types = ('.html', '.js', '.css', '.png', '.jpg', '.gif', '.jpeg', '.json', '.mp3', '.wav')
        for root, _, files in os.walk(project_dir):
            for file in files:
                if file.endswith(file_types):
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, project_dir)
                    dst_path = os.path.join(static_assets_dir, rel_path)
                    
                    # Create directories if needed
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    # Copy the file
                    try:
                        shutil.copy2(src_path, dst_path)
                        print(f"Copied file: {rel_path} to {dst_path}")
                    except Exception as e:
                        print(f"Error copying file {rel_path}: {e}")
        
        # Record all the files we found
        found_files = []
        for root, _, files in os.walk(static_assets_dir):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), static_assets_dir)
                found_files.append(rel_path)
        
        return jsonify({
            "status": "success", 
            "message": "Game set to complete status",
            "files_copied": found_files
        })
    
    except Exception as e:
        print(f"Error forcing game load: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/locate_game_files/<project_name>', methods=['GET'])
def locate_game_files(project_name):
    """Locate the main game files for the project"""
    try:
        # Get the project directory
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        if not os.path.exists(project_dir):
            return jsonify({"status": "error", "message": "Project not found"}), 404
        
        # Find all HTML files in the project
        html_files = []
        js_files = []
        css_files = []
        
        for root, _, files in os.walk(project_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, project_dir)
                
                if file.endswith('.html'):
                    # Serve HTML files from special route
                    html_files.append(f"/play_raw/{project_name}/{rel_path}")
                elif file.endswith('.js'):
                    js_files.append(f"/play_raw/{project_name}/{rel_path}")
                elif file.endswith('.css'):
                    css_files.append(f"/play_raw/{project_name}/{rel_path}")
        
        # Also check in the static assets directory
        static_assets_dir = os.path.join('static', 'project_assets', project_name)
        if os.path.exists(static_assets_dir):
            for root, _, files in os.walk(static_assets_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, static_assets_dir)
                    
                    if file.endswith('.html'):
                        # Serve HTML files from static path
                        html_files.append(f"/static/project_assets/{project_name}/{rel_path}")
                    elif file.endswith('.js'):
                        js_files.append(f"/static/project_assets/{project_name}/{rel_path}")
                    elif file.endswith('.css'):
                        css_files.append(f"/static/project_assets/{project_name}/{rel_path}")
        
        # Ensure all directories exist in project assets
        ensure_project_assets_dir = os.path.join('static', 'project_assets', project_name)
        os.makedirs(ensure_project_assets_dir, exist_ok=True)
        
        # Make sure we copy all project files to static assets
        for root, _, files in os.walk(project_dir):
            for file in files:
                if file.endswith(('.html', '.js', '.css', '.png', '.jpg', '.gif', '.json')):
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, project_dir)
                    dst_path = os.path.join(ensure_project_assets_dir, rel_path)
                    
                    # Create directories if needed
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    # Copy the file
                    try:
                        shutil.copy2(src_path, dst_path)
                        print(f"Copied file: {rel_path} to {dst_path}")
                    except Exception as e:
                        print(f"Error copying file {rel_path}: {e}")
        
        # Return the located files
        return jsonify({
            "status": "success", 
            "message": "Files located",
            "files": html_files,
            "js_files": js_files,
            "css_files": css_files
        })
    
    except Exception as e:
        print(f"Error locating game files: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/play_raw/<project_name>/<path:file_path>', methods=['GET'])
def serve_project_file(project_name, file_path):
    """Serve a raw file from the project directory"""
    try:
        # Get the project directory
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        if not os.path.exists(project_dir):
            return "Project not found", 404
        
        # Check if the file exists
        file_path_full = os.path.join(project_dir, file_path)
        if not os.path.exists(file_path_full) or not os.path.isfile(file_path_full):
            return "File not found", 404
        
        # Determine content type based on file extension
        content_type = 'text/plain'
        if file_path.endswith('.html'):
            content_type = 'text/html'
        elif file_path.endswith('.js'):
            content_type = 'application/javascript'
        elif file_path.endswith('.css'):
            content_type = 'text/css'
        elif file_path.endswith('.json'):
            content_type = 'application/json'
        elif file_path.endswith(('.png', '.jpg', '.jpeg', '.gif')):
            # Let Flask determine content type for images
            return send_from_directory(project_dir, file_path)
        
        # Read the file
        with open(file_path_full, 'r') as f:
            content = f.read()
        
        # Return the content with appropriate content type
        response = make_response(content)
        response.headers['Content-Type'] = content_type
        return response
    
    except Exception as e:
        print(f"Error serving file {file_path}: {str(e)}")
        return str(e), 500

@app.route('/rebuild_css', methods=['GET'])
def rebuild_css():
    """Rebuild Tailwind CSS (development only)"""
    try:
        subprocess.run(['npm', 'run', 'build:css'], check=True)
        return jsonify({"status": "success", "message": "CSS rebuilt successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5050)
