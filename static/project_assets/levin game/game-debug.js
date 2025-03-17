// Simple debug script to check if scripts are loading
console.log('Debug script loaded successfully');
document.body.style.backgroundColor = 'green';

// Create a simple 3D scene with Three.js
function createTestScene() {
    // Check if THREE is defined
    if (typeof THREE === 'undefined') {
        console.error('THREE is not defined! Three.js library was not loaded properly.');
        document.body.innerHTML += '<div style="color:white; background:red; padding:20px; position:fixed; top:0; left:0; right:0;">THREE.js not loaded properly</div>';
        return;
    }
    
    console.log('THREE is defined, creating test scene');
    
    try {
        // Get the container
        const container = document.getElementById('gameContainer');
        if (!container) {
            console.error('Game container element not found!');
            document.body.innerHTML += '<div style="color:white; background:red; padding:20px; position:fixed; top:0; left:0; right:0;">Game container not found</div>';
            return;
        }
        
        // Create scene
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0000ff);
        
        // Create camera
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 5;
        
        // Create renderer
        const renderer = new THREE.WebGLRenderer();
        renderer.setSize(window.innerWidth, window.innerHeight);
        container.appendChild(renderer.domElement);
        
        // Add a cube
        const geometry = new THREE.BoxGeometry();
        const material = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
        const cube = new THREE.Mesh(geometry, material);
        scene.add(cube);
        
        // Animation loop
        function animate() {
            requestAnimationFrame(animate);
            cube.rotation.x += 0.01;
            cube.rotation.y += 0.01;
            renderer.render(scene, camera);
        }
        
        animate();
        
        console.log('Test scene created successfully');
        document.body.innerHTML += '<div style="color:white; background:green; padding:20px; position:fixed; top:0; left:0; right:0;">Test scene created successfully</div>';
    } catch (error) {
        console.error('Error creating test scene:', error);
        document.body.innerHTML += `<div style="color:white; background:red; padding:20px; position:fixed; top:0; left:0; right:0;">Error: ${error.message}</div>`;
    }
}

// Wait for page to load before creating test scene
window.addEventListener('load', createTestScene);
