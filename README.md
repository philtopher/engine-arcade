# Engine Arcade

A web-based game-building platform that uses GPT Engineer to generate Three.js games based on user descriptions.

## Features

- **Game Generation**: Create custom Three.js games from text descriptions
- **Game Types**: Support for various game types (3D Shooter, Platformer, Racing, Puzzle, Custom)
- **Live Preview**: Real-time game preview with live code generation updates
- **Code Editing**: View and edit generated game code with syntax highlighting
- **Real-time Feedback**: See the progress of game generation in real-time

## Technologies Used

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Game Engine**: Three.js
- **AI Code Generation**: GPT Engineer

## Setup

1. Clone this repository
2. Install the required Python packages: `pip install -r requirements.txt`
3. Configure your OpenAI API key in a `.env` file
4. Run the application: `flask run --port=5050`
5. Open your browser and navigate to `http://localhost:5050`

## Project Structure

- `app.py`: Flask application with backend logic
- `templates/`: HTML templates for the web interface
- `static/`: Static assets (CSS, JS, images)
- `static/project_assets/`: Game assets for generated games
