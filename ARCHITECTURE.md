# Engine Arcade Architecture

This document describes the architecture and workflow of Engine Arcade, a web-based platform that uses GPT Engineer to generate Three.js games based on user descriptions.

## System Overview

Engine Arcade consists of two main components:

1. **Frontend**: A Flask web application that provides the user interface
2. **Backend**: GPT Engineer, which handles game code generation via AI

![Architecture Diagram](https://mermaid.ink/img/pako:eNp1kk1PwzAMhv9KlBMgdWu3tduBD8GBAwcOSEgcvNRt1M1NqyYFNK3_HbeFIQG-JI79-LVjZwdaCQocHCbdOKWMGQcH0jfN5FPTRQd1I7RrtFrJu6qTgWx0KLI-ZXONjxIizp5KtOT5P1_JPgNkrV6k9kpW-OfznEvT1HrJrLbUr3_wdZPsLSLZDGNKwXiNYtHAGHkZ8JW8o9UmCFkHF0XLrLGkKpSYQpTRSXaOwbC1o9BVKFH3FLZGEWPp2o-oHQ_UDZ7jkIzb7Eow9XHGQ0ebmY44JzTLImctEiYcPSS-BMUOC6QJQwMpcByaFHhW5HnOUPtGdtwTGgJJKMRl2zzAa9b9aIZPiR7PczDhV72YplIaTe9QHn5B88OYmJMMKcY8YvlkMsnLfDzJL8b5gYtM_rmbpuPRGRcXebm4FOJc5OXZ9OyEi1FRnN5O84JX2Z-1Pl6p?type=png)

## Data Flow and User Journey

### 1. User Initiates Game Creation

- User enters a game description on the web interface (e.g., "make a zombie game")
- Frontend sends this description to the Flask backend via AJAX
- No explicit game type selection is required - the system infers the game type from the description

### 2. Backend Processing

- Flask backend:
  - Creates a new project directory
  - Enhances the user prompt with Three.js-specific context
  - Calls GPT Engineer via shell script

### 3. GPT Engineer Game Generation

- GPT Engineer:
  - Takes the enhanced prompt
  - Combines it with prepared prompts (stored in `/preprompts`)
  - Sends requests to OpenAI API
  - Receives AI responses with game code
  - Writes files (HTML, JavaScript, CSS) to the project directory

### 4. Real-Time Feedback

- Server-Sent Events (SSE) endpoint streams log updates to frontend
- Frontend displays progress and log content in real-time
- Progress bar updates based on recognized milestones in the logs

### 5. Game Rendering

- Once generation is complete, the generated game is loaded in an iframe
- The game uses Three.js for rendering 3D graphics
- Game files are served directly from the filesystem

### 6. Iterative Refinement

- Chat interface allows users to request changes
- These change requests are processed by GPT Engineer
- Updates are applied to the game in real-time

## Key Components

### Flask Backend (`app.py`)

- Routes for game creation, viewing, and playing
- Integration with GPT Engineer
- Log streaming via Server-Sent Events
- Static file serving

### Frontend Templates

- `index.html`: Main page for creating and listing games
- `project.html`: For viewing and managing game code
- `play_game.html`: For playing and iterating on games

### GPT Engineer Integration

- Custom prompt enhancement for Three.js games
- Shell script interface between Flask and GPT Engineer
- Environment variable management for API keys

## Prompt Processing

1. **User Input**: Raw description from web form
2. **Prompt Enhancement**: Backend adds Three.js context and constraints
3. **GPT Engineer Processing**: 
   - User prompt + preprompts → OpenAI API
   - Multiple AI calls with different roles (clarify, generate, improve)
4. **Output Processing**: Structured code generation

## Real-Time Log Streaming

```
Frontend (EventSource) ←-- SSE Stream --- Backend (Flask)
                                          ↑
                                          | Monitors
                                          ↓
                                  GPT Engineer Logs
```

1. Frontend establishes SSE connection
2. Backend monitors log file changes
3. Log updates are streamed in real-time
4. Frontend parses logs to update UI

## Chat Module for Iteration

The chat interface allows users to:
1. Ask questions about their game
2. Request specific changes to game mechanics
3. Debug issues with the generated code
4. Test different variations of the game

Each chat message triggers a new AI interaction that modifies the game code.

## AI Integration Points

1. **Initial Game Generation**: OpenAI API via GPT Engineer
2. **Code Refinement**: Iterative improvements via chat interface
3. **Error Correction**: AI debugging support
4. **Game Enhancement**: Feature additions through natural language requests

## Technical Implementation Details

### Real-Time Streaming

```python
# Backend implementation (Flask)
@app.route('/stream_logs/<project_name>')
def stream_logs(project_name):
    def generate():
        yield f"data: {{\"status\": \"started\", \"message\": \"Starting log stream for {project_name}\"}}\n\n"
        logfile = f"{project_dir}/gpt_engineer.log"
        
        # Stream log file updates in real-time
        with open(logfile, 'r') as f:
            # [Implementation details]
            
    return Response(generate(), mimetype='text/event-stream')
```

```javascript
// Frontend implementation
function setupLogStreaming(projectName) {
    window.logEventSource = new EventSource(`/stream_logs/${projectName}`);
    window.logEventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        // [Implementation details]
    };
}
```

### GPT Engineer Execution

```bash
# run_gpt_engineer.sh
#!/bin/bash
PROJECT_DIR="$1"
GPTE_DIR="$(dirname "$0")/gpt-engineer"

# Load API key from .env
source "$GPTE_DIR/.env"

# Run GPT Engineer with project directory
cd "$GPTE_DIR" && python -m gpt_engineer.applications.cli.main "$PROJECT_DIR" --temperature 0.7 --verbose
```

## Game Type Inference Challenges

The system now infers game types from user descriptions rather than using explicit selection. This approach presents several challenges:

1. **Ambiguity in User Prompts**: When a user provides a vague description like "make a zombie game", the system must infer whether this should be a shooter, racing game, or another genre.

2. **Inconsistent Prompting**: Without explicit structure, users may provide widely varying levels of detail, making it harder for the AI to generate consistent code.

3. **Template Selection**: Previously, specific templates could be chosen based on explicit game type. Now, the system must determine the appropriate starting point from context.

4. **Prompt Engineering Complexity**: More sophisticated prompt engineering is required to guide the AI when game type is implicit.

These challenges may contribute to generation errors if:
- The inference mechanism misinterprets the user's intent
- The prepared prompts don't adequately account for vague descriptions
- The AI attempts to blend incompatible game mechanics based on ambiguous instructions

## Deployment Considerations

- OpenAI API key required in `gpt-engineer/.env`
- File permissions for log access
- CPU/memory requirements for large game generations
- Network bandwidth for real-time streaming

---

This architecture is designed to provide a seamless experience for users to create custom Three.js games through natural language descriptions, with real-time feedback and iterative improvements.
