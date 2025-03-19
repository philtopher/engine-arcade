
// Initialize Three.js components with error handling
let scene, camera, renderer, cube;

try {
    // Scene setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);  // Black background

    // Camera setup
    camera = new THREE.PerspectiveCamera(75, 800 / 600, 0.1, 1000);
    camera.position.set(0, 0, 5);  // Position camera at (0, 0, 5)
    camera.lookAt(0, 0, 0);  // Look at origin

    // Renderer setup
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(800, 600);
    renderer.setPixelRatio(window.devicePixelRatio);

    // Add canvas to document
    document.body.appendChild(renderer.domElement);

    // Create a red cube
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshStandardMaterial({ color: 0xff0000 });
    cube = new THREE.Mesh(geometry, material);
    scene.add(cube);

    // Add white ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);
        
        // Rotate cube around Y axis
        cube.rotation.y += 0.01;
        
        renderer.render(scene, camera);
    }

    // Start animation
    animate();

} catch (error) {
    console.error('Error initializing Three.js scene:', error);
    document.body.innerHTML = `<div style="color: red; padding: 20px;">Error: ${error.message}</div>`;
}

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = 800 / 600;
    camera.updateProjectionMatrix();
    renderer.setSize(800, 600);
});
