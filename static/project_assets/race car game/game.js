// Three.js Racing Game

// Set up the scene, camera, and renderer
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x87CEEB); // Sky blue background
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

// Set up camera position
camera.position.set(0, 3, 5);
camera.lookAt(0, 0, 0);

// Add lights
const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
directionalLight.position.set(10, 15, 10);
directionalLight.castShadow = true;
scene.add(directionalLight);

// Create ground/track
const trackWidth = 20;
const trackLength = 100;
const trackGeometry = new THREE.PlaneGeometry(trackWidth, trackLength);
const trackMaterial = new THREE.MeshStandardMaterial({ 
    color: 0x333333, // Dark gray
    roughness: 0.8
});
const track = new THREE.Mesh(trackGeometry, trackMaterial);
track.rotation.x = -Math.PI / 2;
track.receiveShadow = true;
scene.add(track);

// Add track borders
const borderGeometry = new THREE.BoxGeometry(1, 1, trackLength);
const borderMaterial = new THREE.MeshStandardMaterial({ color: 0xff0000 }); // Red

const leftBorder = new THREE.Mesh(borderGeometry, borderMaterial);
leftBorder.position.set(-trackWidth/2, 0.5, 0);
leftBorder.castShadow = true;
leftBorder.receiveShadow = true;
scene.add(leftBorder);

const rightBorder = new THREE.Mesh(borderGeometry, borderMaterial);
rightBorder.position.set(trackWidth/2, 0.5, 0);
rightBorder.castShadow = true;
rightBorder.receiveShadow = true;
scene.add(rightBorder);

// Create car
const carGeometry = new THREE.BoxGeometry(1, 0.5, 2);
const carMaterial = new THREE.MeshStandardMaterial({ color: 0xff0000 }); // Red car
const car = new THREE.Mesh(carGeometry, carMaterial);
car.position.set(0, 0.5, 0);
car.castShadow = true;
car.receiveShadow = true;
scene.add(car);

// Car physics variables
const carState = {
    velocity: 0,
    maxVelocity: 0.5,
    acceleration: 0.01,
    deceleration: 0.005,
    handling: 0.03,
    position: { x: 0, z: 0 }
};

// Controls
const keys = {};
document.addEventListener('keydown', (e) => {
    keys[e.key] = true;
});
document.addEventListener('keyup', (e) => {
    keys[e.key] = false;
});

// Handle window resize
window.addEventListener('resize', () => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
});

// Game loop
function animate() {
    requestAnimationFrame(animate);
    
    // Car controls
    if (keys['ArrowUp'] || keys['w']) {
        carState.velocity = Math.min(carState.velocity + carState.acceleration, carState.maxVelocity);
    } else if (keys['ArrowDown'] || keys['s']) {
        carState.velocity = Math.max(carState.velocity - carState.acceleration, -carState.maxVelocity/2);
    } else {
        // Deceleration when no keys pressed
        if (carState.velocity > 0) {
            carState.velocity = Math.max(carState.velocity - carState.deceleration, 0);
        } else if (carState.velocity < 0) {
            carState.velocity = Math.min(carState.velocity + carState.deceleration, 0);
        }
    }
    
    // Turning
    if (keys['ArrowLeft'] || keys['a']) {
        if (Math.abs(carState.velocity) > 0.05) {
            car.rotation.y += carState.handling;
        }
    }
    if (keys['ArrowRight'] || keys['d']) {
        if (Math.abs(carState.velocity) > 0.05) {
            car.rotation.y -= carState.handling;
        }
    }
    
    // Update car position based on velocity and rotation
    if (Math.abs(carState.velocity) > 0) {
        car.position.x += Math.sin(car.rotation.y) * carState.velocity;
        car.position.z += Math.cos(car.rotation.y) * carState.velocity;
        
        // Check track boundaries
        if (car.position.x > trackWidth/2 - 1) {
            car.position.x = trackWidth/2 - 1;
            carState.velocity *= 0.5; // Slow down when hitting wall
        }
        if (car.position.x < -trackWidth/2 + 1) {
            car.position.x = -trackWidth/2 + 1;
            carState.velocity *= 0.5;
        }
    }
    
    // Update camera to follow car
    camera.position.x = car.position.x;
    camera.position.z = car.position.z + 5;
    camera.lookAt(car.position);
    
    renderer.render(scene, camera);
}

animate();
