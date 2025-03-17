
// Custom Three.js game based on: 3d-shooter
// Description: dogs shooting penguins

// Game initialization
let score = 0;
const scoreElement = document.getElementById('score-value');

// Scene setup
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87CEEB);

// Camera setup
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);

// Determine camera position based on game type
if ("first-person" === "first-person") {
    camera.position.set(0, 1.7, 0); // Eye level
} else if ("first-person" === "side") {
    camera.position.set(10, 5, 0); // Side view for platformers
} else {
    // Default third-person view
    camera.position.set(0, 5, 10);
}

// Renderer setup
const renderer = new THREE.WebGLRenderer({ antialias: true });
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
const groundMaterial = new THREE.MeshStandardMaterial({ 
    color: 0x555555, 
    roughness: 0.8,
    metalness: 0.2
});
const ground = new THREE.Mesh(groundGeometry, groundMaterial);
ground.rotation.x = -Math.PI / 2; // Rotate to be flat
ground.receiveShadow = true;
scene.add(ground);

// Player character
let playerGeometry;
if ("sphere" === "sphere") {
    playerGeometry = new THREE.SphereGeometry(1, 32, 32);
} else {
    // Default to box
    playerGeometry = new THREE.BoxGeometry(1, 2, 1);
}

const playerMaterial = new THREE.MeshStandardMaterial({ 
    color: 0x00ff00, 
    metalness: 0.3,
    roughness: 0.4
});
const player = new THREE.Mesh(playerGeometry, playerMaterial);
player.position.y = 1; // Position on the ground
player.castShadow = true;
scene.add(player);

// Create enemies/obstacles
const enemies = [];
const numEnemies = 10;

for (let i = 0; i < numEnemies; i++) {
    // Randomize enemy shape
    let enemyGeometry;
    const shapeRandom = Math.random();
    
    if (shapeRandom < 0.33) {
        enemyGeometry = new THREE.BoxGeometry(1, 1, 1);
    } else if (shapeRandom < 0.66) {
        enemyGeometry = new THREE.SphereGeometry(0.5, 16, 16);
    } else {
        enemyGeometry = new THREE.ConeGeometry(0.5, 1, 16);
    }
    
    const enemyMaterial = new THREE.MeshStandardMaterial({ color: 0xff0000 });
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
}

// Create collectible items
const collectibles = [];
const numCollectibles = 15;

for (let i = 0; i < numCollectibles; i++) {
    const collectibleGeometry = new THREE.TetrahedronGeometry(0.5);
    const collectibleMaterial = new THREE.MeshStandardMaterial({ 
        color: 0xffff00, // Gold color
        metalness: 0.8,
        roughness: 0.2,
        emissive: 0xffff00,
        emissiveIntensity: 0.2
    });
    
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
}

// Game state
const gameState = {
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
};

// Control setup
document.addEventListener('keydown', (event) => {
    switch(event.code) {
        case 'KeyW': case 'ArrowUp': gameState.moveForward = true; break;
        case 'KeyS': case 'ArrowDown': gameState.moveBackward = true; break;
        case 'KeyA': case 'ArrowLeft': gameState.moveLeft = true; break;
        case 'KeyD': case 'ArrowRight': gameState.moveRight = true; break;
        case 'Space': 
            if (gameState.isOnGround) {
                gameState.playerVelocityY = gameState.jumpForce;
                gameState.isOnGround = false;
            }
            break;
    }
});

document.addEventListener('keyup', (event) => {
    switch(event.code) {
        case 'KeyW': case 'ArrowUp': gameState.moveForward = false; break;
        case 'KeyS': case 'ArrowDown': gameState.moveBackward = false; break;
        case 'KeyA': case 'ArrowLeft': gameState.moveLeft = false; break;
        case 'KeyD': case 'ArrowRight': gameState.moveRight = false; break;
    }
});

// Mouse controls for looking around
document.addEventListener('mousemove', (event) => {
    // Use relative mouse position from center of screen
    gameState.mouseX = (event.clientX / window.innerWidth) * 2 - 1;
    gameState.mouseY = (event.clientY / window.innerHeight) * 2 - 1;
    
    // Only rotate camera in first-person mode
    if ("first-person" === "first-person") {
        player.rotation.y = -gameState.mouseX * Math.PI;
    }
});

// Click for interaction/shooting
document.addEventListener('click', () => {
    // Increment score on click as a simple interaction
    score += 1;
    scoreElement.textContent = score;
    
    // Simple visual feedback
    const flash = new THREE.Mesh(
        new THREE.SphereGeometry(0.2),
        new THREE.MeshBasicMaterial({ color: 0xffff00, transparent: true, opacity: 0.8 })
    );
    
    // Position in front of player
    const direction = new THREE.Vector3(0, 0, -1);
    direction.applyQuaternion(player.quaternion);
    flash.position.copy(player.position).addScaledVector(direction, 2);
    
    scene.add(flash);
    
    // Remove after animation
    setTimeout(() => {
        scene.remove(flash);
    }, 200);
});

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// Collision detection between player and object
function checkCollision(obj1, obj2, minDistance = 1.5) {
    const dx = obj1.position.x - obj2.position.x;
    const dy = obj1.position.y - obj2.position.y;
    const dz = obj1.position.z - obj2.position.z;
    
    const distance = Math.sqrt(dx*dx + dy*dy + dz*dz);
    return distance < minDistance;
}

// Game loop
function animate() {
    requestAnimationFrame(animate);
    
    if (!gameState.gameOver) {
        // Apply gravity
        gameState.playerVelocityY -= gameState.gravity;
        player.position.y += gameState.playerVelocityY;
        
        // Ground collision
        if (player.position.y < 1) {
            player.position.y = 1;
            gameState.playerVelocityY = 0;
            gameState.isOnGround = true;
        }
        
        // Player movement based on facing direction
        const moveX = gameState.moveRight ? 1 : (gameState.moveLeft ? -1 : 0);
        const moveZ = gameState.moveForward ? 1 : (gameState.moveBackward ? -1 : 0);
        
        if ("first-person" === "first-person") {
            // First-person movement relative to player rotation
            const angle = player.rotation.y;
            player.position.x += (moveZ * Math.sin(angle) + moveX * Math.cos(angle)) * gameState.playerSpeed;
            player.position.z += (moveZ * Math.cos(angle) - moveX * Math.sin(angle)) * gameState.playerSpeed;
            
            // Camera follows player position exactly in first-person
            camera.position.copy(player.position);
            camera.position.y += 0.7; // Eye level
            camera.rotation.y = player.rotation.y;
        } else {
            // Third-person/side view direct movement
            player.position.x += moveX * gameState.playerSpeed;
            player.position.z -= moveZ * gameState.playerSpeed;
            
            // Basic camera following
            if ("first-person" === "side") {
                // Side-view camera (platformer style)
                camera.position.x = player.position.x;
                camera.position.z = 15; // Fixed side view
                camera.lookAt(player.position);
            } else {
                // Third-person camera
                const cameraOffset = new THREE.Vector3(0, 5, 10);
                camera.position.copy(player.position).add(cameraOffset);
                camera.lookAt(player.position);
            }
        }
        
        // Enemy animation
        enemies.forEach(enemy => {
            // Move towards player
            const dx = player.position.x - enemy.position.x;
            const dz = player.position.z - enemy.position.z;
            const distance = Math.sqrt(dx*dx + dz*dz);
            
            if (distance > 1) {
                enemy.position.x += (dx / distance) * enemy.userData.speed;
                enemy.position.z += (dz / distance) * enemy.userData.speed;
            }
            
            // Rotate for visual effect
            enemy.rotation.y += enemy.userData.rotationSpeed;
            
            // Check collision with player
            if (checkCollision(player, enemy)) {
                // Handle collision (reduce score)
                score = Math.max(0, score - 5);
                scoreElement.textContent = score;
                
                // Bounce back from player
                enemy.position.x -= (dx / distance) * 2;
                enemy.position.z -= (dz / distance) * 2;
            }
        });
        
        // Collectible animation and collection
        collectibles.forEach((collectible, index) => {
            // Rotate and hover animation
            collectible.rotation.y += collectible.userData.rotationSpeed;
            collectible.rotation.x += collectible.userData.rotationSpeed * 0.5;
            
            // Hover up and down
            const hoverY = Math.sin(Date.now() * collectible.userData.hoverSpeed + collectible.userData.hoverOffset) * 
                          collectible.userData.hoverHeight;
            collectible.position.y = collectible.userData.baseHeight + hoverY;
            
            // Check collision with player
            if (checkCollision(player, collectible)) {
                // Remove collectible and increase score
                scene.remove(collectible);
                collectibles.splice(index, 1);
                
                // Update score
                score += 10;
                scoreElement.textContent = score;
                
                // Visual and sound feedback could be added here
            }
        });
    }
    
    renderer.render(scene, camera);
}

// Game initialization message
console.log("Game loaded! Common controls:");
console.log("WASD: Move | Arrow Keys: Alternative movement | Mouse: Look around");
console.log("Space: Jump | Click: Interact");

// Start the game loop
animate();
