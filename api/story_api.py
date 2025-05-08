import os
import modal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from modules.story_generator import generate_short_story

# Create a Modal App for the story generation API (updated from Stub)
app = modal.App("autoshorts-story-api")

# Create a FastAPI app
web_app = FastAPI()

# Define the request model
class StoryRequest(BaseModel):
    topic: str

# Add CORS middleware to allow requests from any origin
from fastapi.middleware.cors import CORSMiddleware
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Define the story generation endpoint
@web_app.post("/generate_story")
async def generate_story(req: StoryRequest):
    try:
        # Generate a short story based on the topic
        story = generate_short_story(req.topic)
        return {"story": story}
    except Exception as e:
        # Handle any errors that occur during story generation
        raise HTTPException(status_code=500, detail=str(e))

# Create a Modal image with the necessary dependencies
image = (modal.Image.debian_slim()
    .pip_install(
        "fastapi",
        "openai",
        "pydantic",
        "python-multipart",
        "requests",
    )
    # Create empty __init__.py to make modules a proper package (run commands FIRST)
    .run_commands("mkdir -p /root/modules && touch /root/modules/__init__.py")
    # THEN add local files after all run_commands
    .add_local_file("api/modules/story_generator.py", "/root/modules/story_generator.py")
)

# Create a Modal FastAPI app that serves the FastAPI app
@app.function(image=image, secrets=[modal.Secret.from_name("my-openai-secret")])
@modal.asgi_app()
def fastapi_app():
    # Setup OpenAI API key from environment variable
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
    
    # Return the FastAPI app
    return web_app

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(web_app, host="0.0.0.0", port=8000) 